"""Filtros de calidad, peso, nombre y etiquetas."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class FilterBar(QWidget):
    """Controles de la vista. `changed` se emite cuando cambia cualquier criterio."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre")
        self.search.textChanged.connect(lambda _text: self.changed.emit())
        self.quality = QComboBox()
        self.quality.addItem("Todas las calidades", "any")
        self.quality.addItem("4K", "4K")
        self.quality.addItem("HD", "HD")
        self.quality.addItem("Baja", "Low-res")
        self.quality.currentIndexChanged.connect(lambda _index: self.changed.emit())
        self.weight = QComboBox()
        self.weight.addItem("Cualquier peso", "any")
        self.weight.addItem("Menos de 500 KB", "lt500")
        self.weight.addItem("500 KB a 5 MB", "mid")
        self.weight.addItem("Más de 5 MB", "gt5")
        self.weight.currentIndexChanged.connect(lambda _index: self.changed.emit())
        self.tag_box = QVBoxLayout()
        self.tag_box.setSpacing(4)
        self._checks: list[QCheckBox] = []
        self._available: list[str] | None = None
        layout.addWidget(QLabel("Nombre"))
        layout.addWidget(self.search)
        layout.addWidget(QLabel("Calidad"))
        layout.addWidget(self.quality)
        layout.addWidget(QLabel("Peso"))
        layout.addWidget(self.weight)
        tags = QLabel("Etiquetas")
        layout.addWidget(tags)
        hint = QLabel("Debe incluir todas las marcadas.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addLayout(self.tag_box)
        self.set_available_tags([])

    def quality_value(self) -> str:
        return str(self.quality.currentData())

    def weight_value(self) -> str:
        return str(self.weight.currentData())

    def text_value(self) -> str:
        return self.search.text()

    def selected_tags(self) -> list[str]:
        return [box.text() for box in self._checks if box.isChecked()]

    def set_available_tags(self, tags: list[str]) -> None:
        selected = {tag.casefold() for tag in self.selected_tags()}
        if tags == self._available:
            return
        self._available = list(tags)
        self._clear()
        if not tags:
            empty = QLabel("Sin etiquetas todavía")
            empty.setObjectName("Muted")
            self.tag_box.addWidget(empty)
            return
        for tag in tags:
            box = QCheckBox(tag)
            box.setChecked(tag.casefold() in selected)
            box.toggled.connect(lambda _checked: self.changed.emit())
            self._checks.append(box)
            self.tag_box.addWidget(box)

    def _clear(self) -> None:
        while self.tag_box.count():
            item = self.tag_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checks.clear()
