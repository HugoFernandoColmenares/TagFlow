"""Lectura de imágenes con Pillow y métricas visuales con OpenCV."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def quality_tier(width: int, height: int) -> str:
    """Clasifica la resolución como 4K, HD o Low-res.

    4K cubre 3840×2160 en cualquier orientación. HD cubre 1280×720
    en cualquier orientación. El resto queda como Low-res.
    """

    long_side = max(width, height)
    short_side = min(width, height)
    if long_side >= 3840 and short_side >= 2160:
        return "4K"
    if long_side >= 1280 and short_side >= 720:
        return "HD"
    return "Low-res"


def to_rgb(image: Image.Image) -> Image.Image:
    """Pasa la imagen a RGB sobre un fondo oscuro si tiene transparencia."""

    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (28, 31, 38))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def oriented_image(path: Path) -> Image.Image:
    """Abre la imagen y aplica la orientación EXIF sin modificar el archivo."""

    image = Image.open(path)
    original_format = image.format
    try:
        transposed = ImageOps.exif_transpose(image)
    except Exception:
        logger.debug("No se pudo aplicar EXIF en %s", path, exc_info=True)
        return image
    if transposed is not image:
        image.close()
    if transposed.format is None and original_format:
        transposed.format = original_format
    return transposed


def write_thumbnail(source: Image.Image, dest: Path, size: int) -> None:
    """Guarda una miniatura JPEG. `source` no se modifica de forma permanente."""

    frame = to_rgb(source)
    frame.thumbnail((size, size), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.save(dest, "JPEG", quality=82, optimize=True)


def _decode_bgr(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def compute_sharpness(path: Path) -> float | None:
    """Varianza del Laplaciano. Un valor bajo sugiere desenfoque o zonas planas."""

    try:
        image = _decode_bgr(path)
        if image is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        logger.debug("Nitidez no disponible para %s", path, exc_info=True)
        return None


def compute_phash(path: Path) -> str | None:
    """pHash de 64 bits a partir del DCT de OpenCV, en hexadecimal de 16 cifras."""

    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None
        resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
        spectrum = cv2.dct(np.float32(resized))
        block = spectrum[:8, :8]
        median = float(np.median(block))
        bits = (block > median).astype(np.uint8).flatten()
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return f"{value:016x}"
    except Exception:
        logger.debug("pHash no disponible para %s", path, exc_info=True)
        return None
