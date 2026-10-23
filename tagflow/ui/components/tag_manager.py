"""Editor inmediato de etiquetas de la imagen seleccionada."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tagflow.core.database import normalize_tags
from tagflow.core.errors import UserError


class TagManager(QWidget):
    """Chips de etiquetas con alta y baja al momento."""

    changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._tags: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.chips = QVBoxLayout()
        self.chips.setSpacing(4)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Nueva etiqueta")
        self.input.returnPressed.connect(self._add)
        add = QPushButton("Añadir")
        add.clicked.connect(self._add)
        row.addWidget(self.input, 1)
        row.addWidget(add)
        layout.addLayout(self.chips)
        layout.addLayout(row)
        self.set_tags([])

    def tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild()

    def _add(self) -> None:
        text = self.input.text()
        if not text.strip():
            return
        try:
            cleaned = normalize_tags(self._tags + [text])
        except UserError as exc:
            QMessageBox.warning(self, "TagFlow", str(exc))
            return
        self.input.clear()
        self.set_tags(cleaned)
        self.changed.emit(cleaned)

    def _remove(self, tag: str) -> None:
        cleaned = [item for item in self._tags if item.casefold() != tag.casefold()]
        self.set_tags(cleaned)
        self.changed.emit(cleaned)

    def _rebuild(self) -> None:
        while self.chips.count():
            item = self.chips.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._tags:
            empty = QLabel("Esta imagen no tiene etiquetas.")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.chips.addWidget(empty)
            return
        for tag in self._tags:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(tag)
            label.setObjectName("Chip")
            remove = QPushButton("Quitar")
            remove.setProperty("variant", "ghost")
            remove.clicked.connect(lambda _checked=False, value=tag: self._remove(value))
            row_layout.addWidget(label, 0, Qt.AlignmentFlag.AlignLeft)
            row_layout.addStretch(1)
            row_layout.addWidget(remove)
            self.chips.addWidget(row)
