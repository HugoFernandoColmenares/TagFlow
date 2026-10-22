"""Tema Fusion y hoja de estilo empaquetada con la aplicación."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from pylens.utils.config import asset_path


def apply_theme(app: QApplication) -> None:
    """Aplica Fusion, la paleta oscura y la hoja de estilo."""

    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#12141a"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f3efe6"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#12151b"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1c2028"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#f3efe6"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2a303b"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f3efe6"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#e8a54b"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1c1408"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1c2028"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f3efe6"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9a9286"))
    app.setPalette(palette)
    stylesheet = asset_path("style.qss")
    if stylesheet.is_file():
        app.setStyleSheet(stylesheet.read_text(encoding="utf-8"))
