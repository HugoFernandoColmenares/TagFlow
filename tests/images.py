"""Imágenes sintéticas para las pruebas."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def save_swatch(path: Path, size: tuple[int, int], color: str, kind: str = "rect") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    width, height = size
    if kind == "rect":
        draw.rectangle((width * 0.15, height * 0.2, width * 0.8, height * 0.85), fill="white")
    elif kind == "circle":
        draw.ellipse((width * 0.2, height * 0.15, width * 0.75, height * 0.8), fill="navy")
    else:
        draw.line((0, 0, width, height), fill="black", width=max(2, width // 40))
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, quality=95)
    else:
        image.save(path)
    return path


def checkerboard(path: Path, blur: bool = False) -> Path:
    image = Image.new("L", (128, 128), 0)
    pixels = image.load()
    for y in range(128):
        for x in range(128):
            pixels[x, y] = 255 if (x // 4) % 2 == 0 else 0
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=6))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
