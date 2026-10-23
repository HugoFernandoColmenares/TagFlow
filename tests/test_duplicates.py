"""Heurística de nombres y agrupación de hashes."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagflow.core.duplicates import (
    canonical_stem,
    group_by_exact,
    group_by_name,
    group_by_phash,
    hamming,
)
from tagflow.core.models import ImageRecord


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("image", "image"),
        ("image(1)", "image"),
        ("image (2)", "image"),
        ("image - copy", "image"),
        ("image - Copy (2)", "image"),
        ("image (copy)", "image"),
        ("image copy", "image"),
        ("image_copy", "image"),
        ("foto - copia", "foto"),
        ("foto - copia (2)", "foto"),
        ("foto (copia)", "foto"),
        ("vacation-photo", "vacation-photo"),
        ("copyright", "copyright"),
        ("fotocopia", "fotocopia"),
    ],
)
def test_canonical_copy_names(stem: str, expected: str) -> None:
    assert canonical_stem(stem) == expected


def test_name_groups_stay_inside_the_same_folder() -> None:
    first = _record(1, r"D:\fotos\playa.jpg")
    second = _record(2, r"D:\fotos\playa (1).jpg")
    third = _record(3, r"D:\fotos\playa - copia.jpg")
    other = _record(4, r"D:\otras\playa.jpg")
    groups = group_by_name([first, second, third, other])
    assert len(groups) == 1
    assert set(groups[0].image_ids) == {1, 2, 3}


def test_exact_and_visual_groups() -> None:
    left = _record(1, r"D:\fotos\a.jpg", md5="abc", sha256="fff", phash="0000000000000001")
    right = _record(2, r"D:\fotos\b.png", md5="abc", sha256="fff", phash="0000000000000001")
    far = _record(3, r"D:\fotos\c.jpg", md5="zzz", sha256="yyy", phash="ffffffffffffffff")
    exact = group_by_exact([left, right, far])
    visual = group_by_phash([left, right, far], max_distance=8)
    assert [group.image_ids for group in exact] == [(1, 2)]
    assert exact[0].detail.startswith("Mismos bytes")
    assert [group.image_ids for group in visual] == [(1, 2)]
    assert hamming("0000000000000001", "0000000000000001") == 0


def _record(
    image_id: int,
    path: str,
    md5: str | None = None,
    sha256: str | None = None,
    phash: str | None = None,
) -> ImageRecord:
    file_path = Path(path)
    return ImageRecord(
        id=image_id,
        path=path,
        filename=file_path.name,
        folder=str(file_path.parent),
        extension=file_path.suffix.lower(),
        width=10,
        height=10,
        size_bytes=100,
        format="JPEG",
        quality_tier="Low-res",
        bytes_per_pixel=1,
        sharpness=None,
        md5=md5,
        sha256=sha256,
        phash=phash,
        tags=[],
        mtime_ns=1,
        scan_root=str(file_path.parent),
    )
