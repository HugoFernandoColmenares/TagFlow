"""Operaciones de archivo."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from pylens.core.errors import UserError
from pylens.utils.files import (
    group_files,
    optimize_image,
    rename_file,
    sanitize_filename,
    zip_files,
)


def test_rename_keeps_extension_and_rejects_reserved(tmp_path: Path) -> None:
    source = tmp_path / "foto.jpg"
    source.write_bytes(b"abc")
    renamed = rename_file(source, "atardecer")
    assert renamed.name == "atardecer.jpg"
    assert renamed.is_file()
    with pytest.raises(UserError):
        sanitize_filename("CON")


def test_group_moves_and_rolls_back(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    first.write_bytes(b"1")
    second.write_bytes(b"2")
    destination = group_files([first, second], tmp_path / "lote")
    assert [target.name for _source, target in destination] == ["a.jpg", "b.jpg"]
    assert (tmp_path / "lote" / "a.jpg").is_file()

    other_a = tmp_path / "c.jpg"
    other_b = tmp_path / "d.jpg"
    other_a.write_bytes(b"3")
    other_b.write_bytes(b"4")
    real_move = shutil.move
    calls = {"count": 0}

    def flaky(src: str, dst: str) -> str:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError(28, "disco lleno")
        return real_move(src, dst)

    monkeypatch.setattr("pylens.utils.files.shutil.move", flaky)
    with pytest.raises(UserError):
        group_files([other_a, other_b], tmp_path / "otro")
    assert other_a.is_file()
    assert other_b.is_file()


def test_zip_preserves_relative_names(tmp_path: Path) -> None:
    folder = tmp_path / "fotos"
    image = folder / "viaje" / "faro.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"faro")
    archive = zip_files([image], tmp_path / "salida" / "lote.zip", base=folder)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["viaje/faro.jpg"]


def test_optimize_shrinks_noisy_jpeg(tmp_path: Path) -> None:
    path = tmp_path / "ruido.jpg"
    Image.effect_noise((480, 360), 80).convert("RGB").save(path, quality=100)
    before = path.stat().st_size
    old, new = optimize_image(path, quality=45)
    assert old == before
    assert new < before
    assert path.stat().st_size == new
    with Image.open(path) as image:
        assert image.format == "JPEG"
