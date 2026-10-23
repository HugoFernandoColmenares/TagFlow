"""Secciones del sidebar que se pueden plegar y desplegar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class CollapsibleSection(QFrame):
    """Tarjeta con cabecera clicable. Emite `toggled` al cambiar el estado."""

    toggled = Signal(str, bool)

    def __init__(
        self,
        key: str,
        title: str,
        content: QWidget,
        *,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._expanded = expanded
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        header = QFrame()
        header.setObjectName("CollapseHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 2, 0, 2)
        header_row.setSpacing(8)
        self.chevron = QLabel("▾")
        self.chevron.setObjectName("CollapseChevron")
        self.chevron.setFixedWidth(14)
        heading = QLabel(title.upper())
        heading.setObjectName("Section")
        header_row.addWidget(self.chevron)
        header_row.addWidget(heading, 1)
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(content)
        layout.addWidget(header)
        layout.addWidget(self.body)
        self._header = header
        header.mousePressEvent = self._header_pressed  # type: ignore[method-assign]
        self.set_expanded(expanded, emit=False)

    def _header_pressed(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            event.accept()
            return
        QFrame.mousePressEvent(self._header, event)

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, *, emit: bool = True) -> None:
        self._expanded = expanded
        self.body.setVisible(expanded)
        self.chevron.setText("▾" if expanded else "▸")
        self.setProperty("collapsed", not expanded)
        self.style().unpolish(self)
        self.style().polish(self)
        if emit:
            self.toggled.emit(self.key, expanded)
