"""Icono de ventana y de empaquetado."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def draw_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size * 0.08
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size * 0.22,
        fill=(23, 26, 33, 255),
    )
    inset = size * 0.22
    draw.ellipse((inset, inset, size - inset, size - inset), fill=(232, 165, 75, 255))
    inner = size * 0.36
    draw.ellipse((inner, inner, size - inner, size - inner), fill=(23, 26, 33, 255))
    core = size * 0.45
    draw.ellipse((core, core, size - core, size - core), fill=(232, 165, 75, 255))
    return image


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "pylens" / "assets"
    root.mkdir(parents=True, exist_ok=True)
    image = draw_icon(256)
    image.save(root / "icon.png")
    image.save(
        root / "icon.ico",
        sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)],
    )


if __name__ == "__main__":
    main()
