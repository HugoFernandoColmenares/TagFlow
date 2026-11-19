"""Agrupación automática por calidad y acciones con el selector propio."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

import tagflow.ui.main_window as main_window
from tagflow.ui.main_window import MainWindow
from tagflow.utils.config import Settings
from tests.images import save_swatch


def test_pager_buttons_use_primary_background(qapp: QApplication, tmp_path: Path) -> None:
    window = MainWindow(_settings(tmp_path / "datos"))
    try:
        assert window.prev_page.property("variant") == "primary"
        assert window.next_page.property("variant") == "primary"
        assert window.quality_button.text() == "Agrupar por calidad"
    finally:
        window.close()


def test_quality_grouping_creates_folders_and_is_idempotent(
    qapp: QApplication, tmp_path: Path
) -> None:
    library = tmp_path / "biblioteca"
    save_swatch(library / "grande.jpg", (3840, 2160), "orange")
    save_swatch(library / "uno" / "foto.jpg", (1920, 1080), "steelblue", "circle")
    save_swatch(library / "dos" / "foto.jpg", (1920, 1080), "seagreen", "rect")
    save_swatch(library / "baja.png", (640, 480), "purple", "line")
    window = MainWindow(_settings(tmp_path / "datos"))
    window.show()
    QTest.qWait(30)
    window.load_folder(library)
    _wait_idle(window)
    assert window.image_count() == 4

    grande = next(
        record for record in window.db.list_root(str(library.resolve())) if record.filename == "grande.jpg"
    )
    assert grande.id is not None
    window.gallery.clear_marks()
    window.gallery._on_clicked(grande.id)
    window.gallery._checked.add(grande.id)

    marked = window.quality_records()
    assert [record.filename for record in marked] == ["grande.jpg"]
    summary = window.group_by_quality()
    assert [(tier, moved) for tier, _folder, moved in summary] == [("4K", 1)]
    assert (library / "4K" / "grande.jpg").is_file()
    assert not (library / "HD").exists()

    window.gallery.clear_marks()
    summary = window.group_by_quality()
    counts = {tier: moved for tier, _folder, moved in summary}
    assert counts == {"4K": 0, "HD": 2, "Low-res": 1}
    assert (library / "4K" / "grande.jpg").is_file()
    assert (library / "HD" / "foto.jpg").is_file()
    assert (library / "HD" / "foto (1).jpg").is_file()
    assert (library / "Baja" / "baja.png").is_file()

    paths = {record.path for record in window.db.list_root(str(library.resolve()))}
    assert str((library / "HD" / "foto (1).jpg").resolve()) in paths

    window.gallery.clear_marks()
    summary = window.group_by_quality()
    assert {tier: moved for tier, _folder, moved in summary} == {
        "4K": 0,
        "HD": 0,
        "Low-res": 0,
    }
    assert (library / "HD" / "foto.jpg").is_file()
    assert (library / "HD" / "foto (1).jpg").is_file()
    window.close()


def test_prompts_use_the_in_app_picker(
    qapp: QApplication, tmp_path: Path, monkeypatch
) -> None:
    library = tmp_path / "biblioteca"
    save_swatch(library / "foto.jpg", (1280, 720), "orange")
    window = MainWindow(_settings(tmp_path / "datos"))
    window.show()
    QTest.qWait(30)
    window.load_folder(library)
    _wait_idle(window)

    moved_to = tmp_path / "destino"
    archive = tmp_path / "copia.zip"

    class StubPicker:
        def __init__(self, *args, **kwargs) -> None:
            self.file_mode = "file_name" in kwargs

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def selected_folder(self) -> Path:
            return moved_to

        def selected_path(self) -> Path:
            return archive

    monkeypatch.setattr(main_window, "FolderPickerDialog", StubPicker)
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *args, **kwargs: main_window.QMessageBox.StandardButton.Yes,
    )

    window._prompt_move()
    assert (moved_to / "foto.jpg").is_file()
    assert window.db.get_by_path(str((moved_to / "foto.jpg").resolve())) is not None

    window._prompt_zip()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["foto.jpg"]

    window._prompt_quality()
    assert (library / "HD" / "foto.jpg").is_file()
    window.close()


def _settings(data: Path) -> Settings:
    return Settings(
        data_dir=data,
        db_path=data / "tagflow.sqlite3",
        log_path=data / "tagflow.log",
        log_level="WARNING",
        thumb_size=96,
    )


def _wait_idle(window: MainWindow, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            QApplication.processEvents()
            return
        QTest.qWait(40)
    raise AssertionError("la ventana siguió ocupada")
