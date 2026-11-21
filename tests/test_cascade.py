"""Cascada por calidad: rendimiento local, reutilización y tolerancia a fallos."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

import tagflow.ui.main_window as main_window
from tagflow.core.cascade import (
    cascade_group_by_quality,
    group_folder_by_quality,
    list_cascade_targets,
)
from tagflow.ui.main_window import MainWindow
from tagflow.utils.config import Settings
from tests.images import save_swatch


def test_list_cascade_targets_skips_quality_dirs(tmp_path: Path) -> None:
    base = tmp_path / "base"
    (base / "Serie A").mkdir(parents=True)
    (base / "Serie B").mkdir()
    (base / "4K").mkdir()
    (base / "HD").mkdir()
    (base / "Baja").mkdir()
    (base / ".oculta").mkdir()
    names = [path.name for path in list_cascade_targets(base)]
    assert names == ["Serie A", "Serie B"]


def test_group_folder_reuses_quality_dirs_and_skips_organized(tmp_path: Path) -> None:
    folder = tmp_path / "serie"
    (folder / "4K").mkdir(parents=True)
    (folder / "HD").mkdir()
    save_swatch(folder / "4K" / "ya.jpg", (3840, 2160), "orange")
    save_swatch(folder / "nueva_4k.jpg", (3840, 2160), "red")
    save_swatch(folder / "sub" / "hd.jpg", (1920, 1080), "blue")
    (folder / "nota.txt").write_text("no soy imagen", encoding="utf-8")

    before = (folder / "4K").resolve()
    result = group_folder_by_quality(folder)
    assert result.moved == {"4K": 1, "HD": 1}
    assert (folder / "4K").resolve() == before
    assert (folder / "4K" / "ya.jpg").is_file()
    assert (folder / "4K" / "nueva_4k.jpg").is_file()
    assert (folder / "HD" / "hd.jpg").is_file()
    assert not (folder / "nueva_4k.jpg").exists()


def test_cascade_continues_after_folder_errors(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base"
    good = base / "buena"
    bad = base / "mala"
    good.mkdir(parents=True)
    bad.mkdir()
    save_swatch(good / "foto.jpg", (1280, 720), "steelblue")
    save_swatch(bad / "x.jpg", (640, 480), "purple")

    real = group_folder_by_quality

    def flaky(folder: Path, **kwargs):
        if folder.name == "mala":
            raise RuntimeError("fallo simulado")
        return real(folder, **kwargs)

    monkeypatch.setattr("tagflow.core.cascade.group_folder_by_quality", flaky)
    outcome = cascade_group_by_quality(base)
    assert len(outcome.folders) == 2
    by_name = {item.folder.name: item for item in outcome.folders}
    assert by_name["buena"].moved_total == 1
    assert by_name["mala"].errors
    assert (good / "HD" / "foto.jpg").is_file()


def test_cascade_ui_uses_in_app_picker_and_worker(
    qapp: QApplication, tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "biblioteca"
    one = base / "Alpha"
    two = base / "Beta"
    one.mkdir(parents=True)
    two.mkdir()
    save_swatch(one / "a.jpg", (3840, 2160), "orange")
    save_swatch(two / "b.jpg", (800, 600), "green")

    window = MainWindow(_settings(tmp_path / "datos"))
    window.show()
    QTest.qWait(30)

    class StubPicker:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def selected_folder(self) -> Path:
            return base

    monkeypatch.setattr(main_window, "FolderPickerDialog", StubPicker)
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *args, **kwargs: main_window.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args, **kwargs: None)

    window._prompt_cascade()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            break
        QTest.qWait(40)
    assert not window.is_busy()
    assert window._last_cascade is not None
    assert window._last_cascade.moved_total == 2
    assert (one / "4K" / "a.jpg").is_file()
    assert (two / "Baja" / "b.jpg").is_file()
    window.close()


def _settings(data: Path) -> Settings:
    return Settings(
        data_dir=data,
        db_path=data / "tagflow.sqlite3",
        log_path=data / "tagflow.log",
        log_level="WARNING",
        thumb_size=64,
    )
