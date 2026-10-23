"""Estadísticas sobre el índice, sin recorrer el disco otra vez."""

from __future__ import annotations

from tagflow.core.analytics import folder_depth, summarize
from tagflow.core.models import ImageRecord


def test_summary_counts_formats_tags_and_depth() -> None:
    root = r"D:\biblioteca"
    records = [
        _image(root, root, "a.jpg", "JPEG", "HD", 1000, ["Paisaje", "viaje"]),
        _image(root, root + r"\costa", "b.png", "PNG", "4K", 3000, ["paisaje"]),
        _image(root, root + r"\costa\norte", "c.jpg", "JPEG", "Low-res", 500, []),
    ]
    stats = summarize(records)
    assert stats.count == 3
    assert stats.total_bytes == 4500
    assert stats.dominant_format == "JPEG"
    assert stats.formats[0] == ("JPEG", 2)
    assert stats.qualities["4K"] == 1
    assert stats.qualities["HD"] == 1
    assert stats.tags[0][0].casefold() == "paisaje"
    assert stats.tags[0][1] == 2
    assert stats.max_depth == 2
    assert folder_depth(root, root) == 0


def test_empty_summary() -> None:
    stats = summarize([])
    assert stats.count == 0
    assert stats.dominant_format is None


def _image(
    root: str,
    folder: str,
    name: str,
    fmt: str,
    tier: str,
    size: int,
    tags: list[str],
) -> ImageRecord:
    return ImageRecord(
        path=folder + "\\" + name,
        filename=name,
        folder=folder,
        extension="." + name.rsplit(".", 1)[1],
        width=100,
        height=80,
        size_bytes=size,
        format=fmt,
        quality_tier=tier,
        bytes_per_pixel=size / 8000,
        sharpness=10,
        md5=None,
        sha256=None,
        phash=None,
        tags=tags,
        mtime_ns=1,
        scan_root=root,
    )
