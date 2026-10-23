"""Escaneo, calidad visual y metadatos."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagflow.core.errors import ScanError
from tagflow.core.imaging import compute_phash, compute_sharpness, quality_tier
from tagflow.core.scanner import discover_images, extract_metadata
from tests.images import checkerboard, save_swatch


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((3840, 2160), "4K"),
        ((2160, 3840), "4K"),
        ((1920, 1080), "HD"),
        ((1080, 1920), "HD"),
        ((1280, 720), "HD"),
        ((800, 600), "Low-res"),
    ],
)
def test_quality_tiers(size: tuple[int, int], expected: str) -> None:
    assert quality_tier(*size) == expected


def test_discover_nested_images_and_skips_other_files(tmp_path: Path) -> None:
    root = tmp_path / "fotos"
    save_swatch(root / "a.jpg", (32, 24), "red")
    save_swatch(root / "sub" / "b.png", (32, 24), "blue", "circle")
    (root / "notas.txt").write_text("hola", encoding="utf-8")
    found, problems = discover_images(root)
    names = sorted(path.name for path in found)
    assert names == ["a.jpg", "b.png"]
    assert problems == []


def test_discover_records_permission_errors(monkeypatch, tmp_path: Path) -> None:
    def fake_walk(root, onerror=None, followlinks=False):  # type: ignore[no-untyped-def]
        if onerror:
            onerror(PermissionError(13, "Acceso denegado", str(tmp_path / "privada")))
        yield str(tmp_path), [], []

    monkeypatch.setattr("tagflow.core.scanner.os.walk", fake_walk)
    found, problems = discover_images(tmp_path)
    assert found == []
    assert problems
    assert "permiso" in problems[0][1].lower()


def test_corrupt_file_is_reported(tmp_path: Path) -> None:
    image = tmp_path / "rota.jpg"
    image.write_bytes(b"esto no es una imagen")
    with pytest.raises(ScanError):
        extract_metadata(image, tmp_path, tmp_path / "thumbs", 64)


def test_extract_reads_dimensions_and_thumbnail(tmp_path: Path) -> None:
    image = save_swatch(tmp_path / "playa.jpg", (320, 200), "orange")
    record = extract_metadata(image, tmp_path, tmp_path / "thumbs", 80)
    assert (record.width, record.height) == (320, 200)
    assert record.quality_tier == "Low-res"
    assert record.format == "JPEG"
    assert record.thumb_path is not None
    assert Path(record.thumb_path).is_file()
    assert record.sharpness is None
    measured = extract_metadata(
        image, tmp_path, tmp_path / "thumbs", 80, measure_sharpness=True
    )
    assert measured.sharpness is not None


def test_sharpness_drops_when_blurred(tmp_path: Path) -> None:
    sharp = checkerboard(tmp_path / "nitida.png")
    blurred = checkerboard(tmp_path / "borrosa.png", blur=True)
    assert compute_sharpness(sharp) > compute_sharpness(blurred) * 2


def test_phash_matches_format_variants_and_rejects_other_scenes(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    from tagflow.core.duplicates import hamming

    scene = Image.new("RGB", (160, 120), "white")
    draw = ImageDraw.Draw(scene)
    draw.rectangle((12, 16, 90, 100), fill="black")
    draw.ellipse((50, 20, 140, 90), fill=(180, 40, 40))
    png = tmp_path / "escena.png"
    jpg = tmp_path / "escena.jpg"
    scene.save(png)
    scene.save(jpg, quality=95)
    other = Image.new("RGB", (160, 120), "white")
    ImageDraw.Draw(other).line((0, 0, 160, 120), fill="navy", width=10)
    other_path = tmp_path / "otra.png"
    other.save(other_path)
    left = compute_phash(png)
    right = compute_phash(jpg)
    distant = compute_phash(other_path)
    assert left and right and distant
    assert hamming(left, right) <= 8
    assert hamming(left, distant) > 8
