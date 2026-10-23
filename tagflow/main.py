"""Punto de entrada de TagFlow."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from tagflow.ui.main_window import MainWindow
from tagflow.ui.theme import apply_theme

logger = logging.getLogger(__name__)


def main() -> int:
    """Arranca la ventana. Un fallo de inicio se muestra y no deja el proceso mudo."""

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv)
        app.setApplicationName("TagFlow")
        app.setOrganizationName("TagFlow")
        apply_theme(app)
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        logger.exception("Fallo al iniciar TagFlow")
        _fatal(str(exc))
        return 1


def _fatal(message: str) -> None:
    if QApplication.instance() is None:
        QApplication(sys.argv)
    QMessageBox.critical(None, "TagFlow", f"TagFlow no pudo iniciarse.\n\n{message}")


if __name__ == "__main__":
    raise SystemExit(main())
