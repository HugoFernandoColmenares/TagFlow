"""Capa que cubre el área de trabajo mientras corre un análisis o comparación."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from tagflow.ui.components.spinner import Spinner


class BusyOverlay(QFrame):
    """Oscurece el panel central, bloquea clics y explica qué está pasando."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BusyOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.addStretch(1)
        panel = QFrame()
        panel.setObjectName("BusyPanel")
        panel.setMaximumWidth(420)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 28, 28, 28)
        panel_layout.setSpacing(14)
        self.spinner = Spinner(52)
        self.title = QLabel("Trabajando…")
        self.title.setObjectName("BusyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.hint = QLabel("Las operaciones de la galería quedan en pausa hasta que termine.")
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.title)
        panel_layout.addWidget(self.detail)
        panel_layout.addWidget(self.progress)
        panel_layout.addWidget(self.hint)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def show_busy(self, title: str, detail: str = "") -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.progress.setRange(0, 0)
        self.spinner.start()
        self.show()
        self.raise_()

    def set_progress(self, current: int, total: int, detail: str | None = None) -> None:
        if total <= 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(min(current, total))
        if detail is not None:
            self.detail.setText(detail)

    def hide_busy(self) -> None:
        self.spinner.stop()
        self.hide()
