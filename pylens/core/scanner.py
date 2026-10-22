"""Recorrido de carpetas y extracción de metadatos de imagen."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from pylens.core.errors import ScanError
from pylens.core.imaging import (
    compute_sharpness,
    oriented_image,
    quality_tier,
    write_thumbnail,
)
from pylens.core.models import ImageRecord

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}


def discover_images(
    root: Path,
    skip_dir: Path | None = None,
) -> tuple[list[Path], list[tuple[str, str]]]:
    """Devuelve las imágenes legibles y los problemas de permiso, sin detenerse."""

    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ScanError(str(root), "La carpeta no existe o no es un directorio.")
    skip = skip_dir.resolve() if skip_dir else None
    found: list[Path] = []
    problems: list[tuple[str, str]] = []

    def on_error(error: OSError) -> None:
        location = str(getattr(error, "filename", "") or root)
        problems.append((location, f"Sin permiso para leer: {error.strerror or error}"))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        current = Path(dirpath)
        if skip and (current == skip or skip in current.parents):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and (skip is None or current / name != skip)
        )
        for name in sorted(filenames):
            path = current / name
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                if path.is_file():
                    found.append(path.resolve())
            except OSError as exc:
                problems.append((str(path), f"Sin permiso para leer: {exc.strerror or exc}"))
    return found, problems


def _thumb_destination(thumb_dir: Path, path: Path, mtime_ns: int) -> Path:
    digest = f"{path.as_posix().casefold()}|{mtime_ns}"
    key = hashlib.sha1(digest.encode("utf-8")).hexdigest()[:24]
    return thumb_dir / f"{key}.jpg"


def refresh_thumbnail(path: Path, thumb_dir: Path, thumb_size: int) -> str | None:
    """Regenera la miniatura tras mover, renombrar u optimizar."""

    path = path.resolve()
    image = oriented_image(path)
    try:
        destination = _thumb_destination(thumb_dir, path, path.stat().st_mtime_ns)
        write_thumbnail(image, destination, thumb_size)
    finally:
        image.close()
    return str(destination)


def extract_metadata(
    path: Path,
    scan_root: Path,
    thumb_dir: Path,
    thumb_size: int,
) -> ImageRecord:
    """Lee dimensiones, peso, formato y miniatura. No calcula hashes."""

    path = path.resolve()
    scan_root = scan_root.resolve()
    try:
        stat = path.stat()
    except OSError as exc:
        raise ScanError(str(path), f"No pude leer el archivo: {exc.strerror or exc}") from exc
    if stat.st_size <= 0:
        raise ScanError(str(path), "El archivo está vacío.")
    try:
        image = oriented_image(path)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ScanError(
            str(path),
            "No pude leer la imagen (archivo dañado o formato no reconocido).",
        ) from exc
    try:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ScanError(str(path), "La imagen no tiene dimensiones válidas.")
        fmt = (image.format or path.suffix.removeprefix(".")).upper()
        if fmt in {"JPG", "JPEG"}:
            fmt = "JPEG"
        thumb = _thumb_destination(thumb_dir, path, stat.st_mtime_ns)
        try:
            write_thumbnail(image, thumb, thumb_size)
            thumb_path: str | None = str(thumb)
        except OSError:
            logger.warning("No pude guardar la miniatura de %s", path, exc_info=True)
            thumb_path = None
    finally:
        image.close()
    sharpness = compute_sharpness(path)
    pixels = width * height
    return ImageRecord(
        path=str(path),
        filename=path.name,
        folder=str(path.parent),
        extension=path.suffix.lower(),
        width=width,
        height=height,
        size_bytes=stat.st_size,
        format=fmt,
        quality_tier=quality_tier(width, height),
        bytes_per_pixel=stat.st_size / pixels,
        sharpness=sharpness,
        md5=None,
        sha256=None,
        phash=None,
        tags=[],
        mtime_ns=stat.st_mtime_ns,
        scan_root=str(scan_root),
        thumb_path=thumb_path,
    )
