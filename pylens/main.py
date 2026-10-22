"""Punto de entrada de PyLens."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from pylens.ui.main_window import MainWindow
from pylens.ui.theme import apply_theme

logger = logging.getLogger(__name__)


def main() -> int:
    """Arranca la ventana. Un fallo de inicio se muestra y no deja el proceso mudo."""

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv)
        app.setApplicationName("PyLens")
        app.setOrganizationName("PyLens")
        apply_theme(app)
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        logger.exception("Fallo al iniciar PyLens")
        _fatal(str(exc))
        return 1


def _fatal(message: str) -> None:
    if QApplication.instance() is None:
        QApplication(sys.argv)
    QMessageBox.critical(None, "PyLens", f"PyLens no pudo iniciarse.\n\n{message}")


if __name__ == "__main__":
    raise SystemExit(main())
