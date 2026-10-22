"""La ventana usa el índice, los filtros y las operaciones de verdad."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pylens.ui.main_window import MainWindow
from pylens.utils.config import Settings
from tests.images import save_swatch


def test_window_indexes_filters_tags_and_file_operations(qapp: QApplication, tmp_path: Path) -> None:
    library = tmp_path / "biblioteca"
    save_swatch(library / "playa.jpg", (640, 480), "orange")
    save_swatch(library / "playa (1).jpg", (640, 480), "orange")
    save_swatch(library / "sub" / "ciudad.png", (1280, 720), "steelblue", "circle")
    (library / "rota.jpg").write_bytes(b"no soy una imagen")
    settings = _settings(tmp_path / "datos")
    window = MainWindow(settings)
    window.show()
    QTest.qWait(30)
    window.load_folder(library)
    _wait_idle(window)
    assert window.image_count() == 3
    assert window.db.count_errors() >= 1
    assert window.stats.summary.text().startswith("3 imágenes")

    playa = next(item for item in window.db.list_root(str(library.resolve())) if item.filename == "playa.jpg")
    assert playa.id is not None
    window.gallery._on_clicked(playa.id)
    window.inspector.tags.input.setText("paisaje")
    window.inspector.tags._add()
    assert window.image_count() == 3
    tagged = window.db.get_by_id(playa.id)
    assert tagged is not None and tagged.tags == ["paisaje"]

    tag_box = next(box for box in window.filters._checks if box.text() == "paisaje")
    tag_box.setChecked(True)
    QApplication.processEvents()
    assert window.image_count() == 1
    tag_box.setChecked(False)
    QApplication.processEvents()

    window.filters.quality.setCurrentIndex(window.filters.quality.findData("HD"))
    QApplication.processEvents()
    assert window.image_count() == 1
    assert window.gallery.selected() is not None
    assert window.gallery.selected().filename == "ciudad.png"
    window.filters.quality.setCurrentIndex(0)
    QApplication.processEvents()

    window.exact_check.setChecked(False)
    window.visual_check.setChecked(False)
    window.find_duplicates(show_dialog=False)
    _wait_idle(window)
    groups = window.collect_groups()
    assert any(set(group.image_ids) >= {playa.id} and group.kind == "name" for group in groups)

    window.gallery.clear_marks()
    window.gallery._on_clicked(playa.id)
    window.rename_selected("costa")
    renamed = library / "costa.jpg"
    assert renamed.is_file()
    costa = window.db.get_by_path(str(renamed.resolve()))
    assert costa is not None and costa.id == playa.id

    window.gallery.clear_marks()
    window.gallery._on_clicked(costa.id)
    destination = window.group_selected("viaje")
    moved = destination / "costa.jpg"
    assert moved.is_file()
    assert (library / "sub" / "ciudad.png").is_file()

    archive = tmp_path / "lote.zip"
    window.zip_selected(archive)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["viaje/costa.jpg"]

    window.gallery.clear_marks()
    window.gallery._on_clicked(costa.id)
    window.optimize_selected(50)
    updated = window.db.get_by_id(costa.id)
    assert updated is not None
    assert updated.size_bytes == moved.stat().st_size
    assert updated.tags == ["paisaje"]

    window.delete_ids([costa.id])
    assert not moved.exists()
    assert window.db.get_by_id(costa.id) is None

    window.close()
    reopened = MainWindow(settings)
    reopened.show()
    QTest.qWait(30)
    assert not reopened.is_busy()
    assert reopened.image_count() == 2
    reopened.close()


def _settings(data: Path) -> Settings:
    return Settings(
        data_dir=data,
        db_path=data / "pylens.sqlite3",
        log_path=data / "pylens.log",
        log_level="WARNING",
        thumb_size=96,
    )


def _wait_idle(window: MainWindow, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            QApplication.processEvents()
            return
        QTest.qWait(40)
    raise AssertionError("la ventana siguió ocupada")
