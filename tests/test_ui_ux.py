"""Overlay de carga y secciones colapsables del sidebar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel

from tagflow.ui.components.busy_overlay import BusyOverlay
from tagflow.ui.components.collapsible import CollapsibleSection
from tagflow.ui.main_window import MainWindow
from tagflow.utils.config import Settings
from tests.images import save_swatch


def test_collapsible_section_toggles(qapp: QApplication) -> None:
    body = QLabel("contenido")
    section = CollapsibleSection("demo", "Filtros", body, expanded=True)
    section.show()
    assert section.is_expanded()
    assert not section.body.isHidden()
    section.toggle()
    assert not section.is_expanded()
    assert section.body.isHidden()
    section.toggle()
    assert section.is_expanded()
    assert not section.body.isHidden()


def test_busy_overlay_blocks_and_reports_progress(qapp: QApplication) -> None:
    overlay = BusyOverlay()
    overlay.show_busy("Indexando carpeta", "Preparando…")
    assert overlay.isVisible()
    overlay.set_progress(12, 40, "12 de 40 archivos")
    assert overlay.progress.maximum() == 40
    assert overlay.progress.value() == 12
    assert "12 de 40" in overlay.detail.text()
    overlay.hide_busy()
    assert overlay.isHidden()


def test_window_shows_workspace_loader_while_scanning(
    qapp: QApplication, tmp_path: Path
) -> None:
    library = tmp_path / "lib"
    for index in range(8):
        save_swatch(library / f"f_{index}.jpg", (48, 36), "olive")
    settings = Settings(
        data_dir=tmp_path / "datos",
        db_path=tmp_path / "datos" / "tagflow.sqlite3",
        log_path=tmp_path / "datos" / "tagflow.log",
        log_level="WARNING",
        thumb_size=64,
    )
    window = MainWindow(settings)
    window.show()
    window.load_folder(library)
    assert window.busy_overlay.isVisible()
    assert not window.open_button.isEnabled()
    assert window._sidebar_sections["folder"].is_expanded()
    window._sidebar_sections["filters"].toggle()
    assert not window._sidebar_sections["filters"].is_expanded()
    assert "filters" in (window.db.get_setting("sidebar_collapsed") or "")
    from PySide6.QtTest import QTest
    import time

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            break
        QTest.qWait(40)
    assert not window.is_busy()
    assert window.busy_overlay.isHidden()
    assert window.open_button.isEnabled()
    window.close()
