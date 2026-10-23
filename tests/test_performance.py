"""Comportamiento con bibliotecas grandes: paginación, lotes y pHash acotado."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tagflow.core.database import Database
from tagflow.core.duplicates import group_by_phash
from tagflow.core.models import ImageRecord
from tagflow.ui.components.gallery import PAGE_SIZE, Gallery
from tagflow.ui.main_window import MainWindow
from tagflow.utils.config import Settings
from tests.images import save_swatch


def test_gallery_only_builds_one_page_of_widgets(qapp: QApplication) -> None:
    gallery = Gallery()
    records = [_record(index, f"foto_{index:05d}.jpg") for index in range(500)]
    gallery.set_images(records)
    assert gallery.image_count() == 500
    assert gallery.card_count() == PAGE_SIZE
    assert gallery.page_count() == (500 + PAGE_SIZE - 1) // PAGE_SIZE
    gallery.next_page()
    assert gallery.page() == 1
    assert gallery.card_count() == PAGE_SIZE


def test_batch_upsert_and_fingerprint_skip(tmp_path: Path) -> None:
    database = Database(tmp_path / "tagflow.sqlite3")
    database.initialize()
    root = str(tmp_path)
    batch = [_record(None, f"img_{index}.jpg", root=root) for index in range(300)]
    started = time.perf_counter()
    database.upsert_batch(batch)
    first = time.perf_counter() - started
    assert database.count_root(root) == 300
    prints = database.fingerprints(root)
    assert len(prints) == 300
    started = time.perf_counter()
    database.upsert_batch(batch)
    second = time.perf_counter() - started
    assert first < 2.0
    assert second < 2.0
    database.close()


def test_phash_grouping_stays_subquadratic() -> None:
    records = []
    for index in range(4000):
        # Prefijos distintos para repartir cubos; cada 40 hay un par casi igual.
        high = (index * 2654435761) & 0xFFFFFFFF
        value = (high << 32) | (index & 0xFFFFF000)
        if index % 40 == 1 and records[-1].phash:
            value = int(records[-1].phash, 16) ^ 0x3
        phash = f"{value:016x}"
        records.append(_record(index + 1, f"x_{index}.jpg", phash=phash))
    started = time.perf_counter()
    groups = group_by_phash(records, max_distance=8)
    elapsed = time.perf_counter() - started
    assert elapsed < 3.0
    assert any(len(group.image_ids) >= 2 for group in groups)


def test_rescan_skips_unchanged_files(qapp: QApplication, tmp_path: Path) -> None:
    library = tmp_path / "lib"
    for index in range(12):
        save_swatch(library / f"foto_{index}.jpg", (64, 48), "teal")
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
    _wait(window)
    assert window.image_count() == 12
    first_pass = window.db.count_root(str(library.resolve()))
    window.load_folder(library)
    _wait(window)
    assert window.db.count_root(str(library.resolve())) == first_pass
    assert window.gallery.card_count() <= PAGE_SIZE
    window.close()


def _wait(window: MainWindow, timeout: float = 30) -> None:
    from PySide6.QtTest import QTest

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            QApplication.processEvents()
            return
        QTest.qWait(40)
    raise AssertionError("la ventana siguió ocupada")


def _record(
    image_id: int | None,
    name: str,
    *,
    root: str = r"D:\lib",
    phash: str | None = None,
) -> ImageRecord:
    return ImageRecord(
        id=image_id,
        path=f"{root}\\{name}",
        filename=name,
        folder=root,
        extension=".jpg",
        width=100,
        height=80,
        size_bytes=1200,
        format="JPEG",
        quality_tier="Low-res",
        bytes_per_pixel=0.15,
        sharpness=None,
        md5=None,
        sha256=None,
        phash=phash,
        tags=[],
        mtime_ns=10,
        scan_root=root,
    )
