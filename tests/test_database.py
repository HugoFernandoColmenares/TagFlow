"""Persistencia SQLite."""

from __future__ import annotations

from pathlib import Path

from tagflow.core.database import Database
from tagflow.core.models import ImageRecord
from tagflow.core.scanner import extract_metadata
from tests.images import save_swatch


def test_filters_tags_and_hash_invalidation(tmp_path: Path) -> None:
    database = Database(tmp_path / "tagflow.sqlite3")
    database.initialize()
    root = str(tmp_path)
    small = _manual(root, "a.jpg", 2_000, "HD", ["Paisaje"], md5="uno")
    large = _manual(root, "b.jpg", 6_000_000, "Low-res", ["retrato"])
    database.upsert_image(small)
    database.upsert_image(large)
    assert [item.filename for item in database.query_images(root, weight="gt5")] == ["b.jpg"]
    assert [item.filename for item in database.query_images(root, weight="lt500")] == ["a.jpg"]
    assert [item.filename for item in database.query_images(root, tags=["paisaje"])] == ["a.jpg"]
    assert [item.filename for item in database.query_images(root, text="b.j")] == ["b.jpg"]
    stored = database.get_by_path(small.path)
    assert stored is not None and stored.md5 == "uno"
    database.update_tags(stored.id or 0, ["paisaje", "paisaje", "viaje"])
    changed = _manual(root, "a.jpg", 2_000, "HD", [], md5=None, mtime_ns=small.mtime_ns)
    kept = database.upsert_image(changed)
    assert kept.tags == ["paisaje", "viaje"]
    assert kept.md5 == "uno"
    replaced = _manual(root, "a.jpg", 9_000, "HD", [], mtime_ns=small.mtime_ns + 5)
    wiped = database.upsert_image(replaced)
    assert wiped.tags == ["paisaje", "viaje"]
    assert wiped.md5 is None
    assert database.prune(root, {large.path}) == 1
    assert database.get_by_path(small.path) is None
    database.log_error("fallo de prueba", path=large.path)
    assert database.count_errors() == 1
    database.close()


def test_real_image_roundtrip_keeps_tags(tmp_path: Path) -> None:
    image = save_swatch(tmp_path / "faro.jpg", (40, 30), "gold")
    database = Database(tmp_path / "data" / "tagflow.sqlite3")
    database.initialize()
    record = extract_metadata(image, tmp_path, tmp_path / "thumbs", 32)
    stored = database.upsert_image(record)
    database.update_tags(stored.id or 0, ["costa"])
    again = database.upsert_image(extract_metadata(image, tmp_path, tmp_path / "thumbs", 32))
    assert again.tags == ["costa"]
    assert again.id == stored.id
    database.close()


def _manual(
    root: str,
    name: str,
    size: int,
    tier: str,
    tags: list[str],
    md5: str | None = None,
    mtime_ns: int = 10,
) -> ImageRecord:
    return ImageRecord(
        path=str(Path(root) / name),
        filename=name,
        folder=root,
        extension=".jpg",
        width=100,
        height=100,
        size_bytes=size,
        format="JPEG",
        quality_tier=tier,
        bytes_per_pixel=size / 10_000,
        sharpness=1,
        md5=md5,
        sha256=None,
        phash=None,
        tags=tags,
        mtime_ns=mtime_ns,
        scan_root=root,
    )
