"""Genera la biblioteca de demostración y guarda capturas de la ventana real."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pylens.ui.components.dialogs import ErrorDialog
from pylens.ui.main_window import MainWindow
from pylens.ui.theme import apply_theme
from pylens.utils.config import Settings

OUT = ROOT / "docs" / "screenshots"


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    ramp = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    color = (1 - ramp) * np.array(top, dtype=np.float32) + ramp * np.array(bottom, dtype=np.float32)
    plane = np.repeat(color.astype(np.uint8), width, axis=1)
    return Image.fromarray(plane, "RGB")


def build_library(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    sunset = gradient((3840, 2160), (28, 36, 74), (232, 122, 58))
    draw = ImageDraw.Draw(sunset)
    draw.ellipse((3000, 280, 3520, 800), fill=(255, 214, 140))
    sunset.save(root / "atardecer.jpg", quality=90)

    ocean = gradient((1920, 1080), (18, 78, 112), (196, 228, 220))
    draw = ImageDraw.Draw(ocean)
    draw.ellipse((180, 220, 860, 900), fill=(14, 52, 84))
    draw.ellipse((980, 140, 1500, 660), outline=(255, 255, 255), width=18)
    ocean.save(root / "oceano.png")

    forest = gradient((1600, 900), (18, 48, 32), (214, 196, 140))
    draw = ImageDraw.Draw(forest)
    for index, x in enumerate(range(80, 1500, 140)):
        draw.rectangle((x, 180 + (index % 3) * 40, x + 46, 820), fill=(12, 42, 28))
    forest.save(root / "bosque.webp", quality=90)

    detail = gradient((640, 480), (92, 64, 48), (232, 214, 190))
    ImageDraw.Draw(detail).rectangle((70, 80, 560, 400), outline=(255, 248, 240), width=8)
    detail.save(root / "detalle.jpg", quality=90)

    width, height = 1700, 1200
    grid = np.indices((height, width))
    texture = ((grid[0] // 24 + grid[1] // 24) % 2) * 180 + 40
    Image.fromarray(texture.astype(np.uint8), "L").convert("RGB").save(root / "textura.bmp")

    beach = Image.new("RGB", (1280, 720), (244, 214, 160))
    draw = ImageDraw.Draw(beach)
    draw.rectangle((0, 430, 1280, 720), fill=(42, 122, 168))
    draw.ellipse((860, 80, 1120, 340), fill=(240, 120, 70))
    beach_path = root / "duplicados" / "playa.jpg"
    beach_path.parent.mkdir(parents=True)
    beach.save(beach_path, quality=95)
    shutil.copy2(beach_path, root / "duplicados" / "playa (1).jpg")
    shutil.copy2(beach_path, root / "duplicados" / "playa - copia.jpg")
    variant = root / "variantes" / "horizonte.png"
    variant.parent.mkdir(parents=True, exist_ok=True)
    beach.save(variant)

    light = gradient((1280, 720), (250, 236, 180), (64, 140, 170))
    ImageDraw.Draw(light).polygon([(640, 80), (180, 640), (1100, 640)], fill=(255, 250, 240))
    lighthouse = root / "sub" / "nivel" / "faro.jpg"
    lighthouse.parent.mkdir(parents=True, exist_ok=True)
    light.save(lighthouse, quality=90)

    broken = root / "dañados" / "nota.jpg"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"esto no es una imagen")


def save_widget(widget, name: str) -> None:
    for _ in range(4):
        QApplication.processEvents()
        QTest.qWait(120)
    image = QImage(widget.size(), QImage.Format.Format_RGB32)
    image.fill(QColor("#12141a"))
    widget.render(image)
    target = OUT / name
    image.save(str(target))
    print(f"captura {target} {image.width()}x{image.height()}")


def wait_idle(window: MainWindow) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.is_busy():
            QApplication.processEvents()
            return
        QTest.qWait(40)
    raise RuntimeError("la ventana no terminó la operación")


def add_tag(window: MainWindow, filename: str, tag: str) -> None:
    assert window.scan_root is not None
    record = next(
        item
        for item in window.db.list_root(str(window.scan_root))
        if item.filename == filename
    )
    assert record.id is not None
    window.gallery._on_clicked(record.id)
    window.inspector.tags.input.setText(tag)
    window.inspector.tags._add()
    QApplication.processEvents()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".pylens-demo"
    library = work / "biblioteca"
    data = work / "datos"
    if data.exists():
        shutil.rmtree(data)
    build_library(library)
    app = QApplication(sys.argv)
    apply_theme(app)
    settings = Settings(
        data_dir=data,
        db_path=data / "pylens.sqlite3",
        log_path=data / "pylens.log",
        log_level="WARNING",
        thumb_size=320,
    )
    window = MainWindow(settings)
    window.setFixedSize(1360, 920)
    window.show()
    save_widget(window, "01-inicio.png")

    window.load_folder(library)
    wait_idle(window)
    for filename in ("atardecer.jpg", "oceano.png", "bosque.webp", "faro.jpg"):
        add_tag(window, filename, "paisaje")
    add_tag(window, "detalle.jpg", "detalle")
    add_tag(window, "playa.jpg", "costa")
    window.exact_check.setChecked(True)
    window.visual_check.setChecked(True)
    window.find_duplicates(show_dialog=False)
    wait_idle(window)

    playa = next(item for item in window.db.list_root(str(window.scan_root)) if item.filename == "playa.jpg")
    assert playa.id is not None
    window.gallery._on_clicked(playa.id)
    save_widget(window, "02-biblioteca.png")
    sidebar = window.findChild(QScrollArea, "SidebarScroll")
    if sidebar is not None:
        sidebar.verticalScrollBar().setValue(sidebar.verticalScrollBar().maximum())
        save_widget(window, "06-estadisticas.png")
        sidebar.verticalScrollBar().setValue(0)

    tag_box = next(box for box in window.filters._checks if box.text() == "paisaje")
    tag_box.setChecked(True)
    QApplication.processEvents()
    save_widget(window, "03-filtros.png")
    tag_box.setChecked(False)
    QApplication.processEvents()

    dialog = window.build_duplicate_dialog()
    if dialog is None:
        raise RuntimeError("no se encontraron duplicados en la demostración")
    dialog.show()
    save_widget(dialog, "04-duplicados.png")
    dialog.close()

    errors = ErrorDialog(window.db.list_errors(), window)
    errors.show()
    save_widget(errors, "05-registro.png")
    errors.close()
    print("grupos", [(group.kind, group.title, len(group.image_ids)) for group in window.collect_groups()])
    window.close()


if __name__ == "__main__":
    main()
