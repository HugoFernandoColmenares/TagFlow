"""Galería paginada: solo materializa las tarjetas de la página visible."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tagflow.core.models import ImageRecord
from tagflow.utils.text import format_bytes, quality_label

PAGE_SIZE = 96


class ImageCard(QFrame):
    """Tarjeta de una imagen: miniatura, datos y casilla de lote."""

    clicked = Signal(int)
    toggled = Signal(int, bool)

    def __init__(self, record: ImageRecord) -> None:
        super().__init__()
        self.record = record
        self.setObjectName("ImageCard")
        self.setProperty("selected", False)
        self.setFixedSize(206, 258)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        self.thumb = QLabel()
        self.thumb.setFixedSize(186, 132)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setPixmap(_thumbnail(record))
        self.name = QLabel()
        self.name.setToolTip(record.filename)
        metrics = QFontMetrics(self.name.font())
        self.name.setText(metrics.elidedText(record.filename, Qt.TextElideMode.ElideMiddle, 170))
        self.meta = QLabel(
            f"{record.width}×{record.height}   ·   {format_bytes(record.size_bytes)}"
        )
        self.meta.setObjectName("Muted")
        row = QHBoxLayout()
        self.check = QCheckBox("Marcar")
        self.check.toggled.connect(self._on_toggle)
        self.tier = QLabel(quality_label(record.quality_tier))
        self.tier.setObjectName("Tier")
        self.tier.setProperty("tier", record.quality_tier)
        row.addWidget(self.check)
        row.addStretch(1)
        row.addWidget(self.tier)
        layout.addWidget(self.thumb)
        layout.addWidget(self.name)
        layout.addWidget(self.meta)
        layout.addLayout(row)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.record.id is not None:
            self.clicked.emit(self.record.id)
        super().mousePressEvent(event)

    def _on_toggle(self, checked: bool) -> None:
        if self.record.id is not None:
            self.toggled.emit(self.record.id, checked)


class Gallery(QScrollArea):
    """Rejilla paginada. Con 14k fotos solo existen ~PAGE_SIZE widgets a la vez."""

    selection_changed = Signal(object)
    open_requested = Signal()
    page_changed = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(8, 8, 8, 16)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self.container)
        self._records: list[ImageRecord] = []
        self._by_id: dict[int, ImageRecord] = {}
        self._cards: dict[int, ImageCard] = {}
        self._checked: set[int] = set()
        self._selected_id: int | None = None
        self._columns = 0
        self._page = 0
        self.empty = self._build_empty()
        self.empty.hide()
        self.grid.addWidget(self.empty, 0, 0)

    def image_count(self) -> int:
        return len(self._records)

    def card_count(self) -> int:
        """Cuántas tarjetas Qt existen ahora (útil para comprobar la paginación)."""

        return len(self._cards)

    def page(self) -> int:
        return self._page

    def page_count(self) -> int:
        if not self._records:
            return 1
        return (len(self._records) + PAGE_SIZE - 1) // PAGE_SIZE

    def selected(self) -> ImageRecord | None:
        if self._selected_id is None:
            return None
        return self._by_id.get(self._selected_id)

    def batch(self) -> list[ImageRecord]:
        if self._checked:
            return [record for record in self._records if record.id in self._checked]
        selected = self.selected()
        return [] if selected is None else [selected]

    def mark_visible(self) -> None:
        for record in self._page_records():
            if record.id is not None:
                self._checked.add(record.id)
        for image_id, card in self._cards.items():
            card.check.blockSignals(True)
            card.check.setChecked(image_id in self._checked)
            card.check.blockSignals(False)

    def clear_marks(self) -> None:
        self._checked.clear()
        for card in self._cards.values():
            card.check.blockSignals(True)
            card.check.setChecked(False)
            card.check.blockSignals(False)

    def set_page(self, page: int) -> None:
        total = self.page_count()
        self._page = max(0, min(page, total - 1))
        self._rebuild_page()
        self.page_changed.emit(self._page, total)

    def next_page(self) -> None:
        self.set_page(self._page + 1)

    def previous_page(self) -> None:
        self.set_page(self._page - 1)

    def set_images(self, records: list[ImageRecord]) -> None:
        previous = self._selected_id
        self._clear_cards()
        self._records = list(records)
        self._by_id = {record.id: record for record in records if record.id is not None}
        self._checked = {image_id for image_id in self._checked if image_id in self._by_id}
        if previous not in self._by_id:
            previous = None
        if previous is not None:
            index = next(
                (i for i, record in enumerate(self._records) if record.id == previous),
                0,
            )
            self._page = index // PAGE_SIZE
        else:
            self._page = 0
        if not self._by_id:
            self._selected_id = None
            self._place_empty()
            self.page_changed.emit(0, 1)
            self.selection_changed.emit(None)
            return
        self.empty.hide()
        self._rebuild_page()
        if previous in self._by_id:
            self._on_clicked(previous)
        else:
            first = self._page_records()[0]
            assert first.id is not None
            self._on_clicked(first.id)
        self.page_changed.emit(self._page, self.page_count())

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if not self._cards:
            self._place_empty()
        else:
            self._reflow()

    def _page_records(self) -> list[ImageRecord]:
        start = self._page * PAGE_SIZE
        return self._records[start : start + PAGE_SIZE]

    def _rebuild_page(self) -> None:
        self._clear_cards()
        if not self._by_id:
            self._place_empty()
            return
        self.empty.hide()
        for record in self._page_records():
            if record.id is None:
                continue
            card = ImageCard(record)
            card.check.setChecked(record.id in self._checked)
            card.clicked.connect(self._on_clicked)
            card.toggled.connect(self._on_toggled)
            self._cards[record.id] = card
        self._columns = 0
        self._reflow()
        if self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)

    def _place_empty(self) -> None:
        self.empty.show()
        if self.grid.indexOf(self.empty) < 0:
            self.grid.addWidget(self.empty, 0, 0)
        self.empty.setMinimumSize(
            max(360, self.viewport().width() - 24),
            max(380, self.viewport().height() - 24),
        )

    def _on_clicked(self, image_id: int) -> None:
        self._selected_id = image_id
        for card_id, card in self._cards.items():
            card.set_selected(card_id == image_id)
        self.selection_changed.emit(self._by_id.get(image_id))

    def _on_toggled(self, image_id: int, checked: bool) -> None:
        if checked:
            self._checked.add(image_id)
        else:
            self._checked.discard(image_id)
        self._on_clicked(image_id)

    def _reflow(self) -> None:
        if not self._cards:
            return
        columns = max(1, (self.viewport().width() - 16) // 218)
        if columns == self._columns and self.grid.count() == len(self._cards):
            return
        self._columns = columns
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.empty:
                self.grid.removeWidget(widget)
        for index, record in enumerate(self._page_records()):
            if record.id is None:
                continue
            card = self._cards.get(record.id)
            if card is not None:
                self.grid.addWidget(card, index // columns, index % columns)

    def _clear_cards(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is None or widget is self.empty:
                continue
            widget.hide()
            widget.deleteLater()
        self._cards.clear()

    def _build_empty(self) -> QWidget:
        box = QWidget()
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(10)
        title = QLabel("Nada indexado en esta vista")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(
            "Abre una carpeta para leer sus imágenes en segundo plano. "
            "El índice, las etiquetas y los duplicados se quedan en este equipo."
        )
        body.setObjectName("Muted")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setMaximumWidth(460)
        button = QPushButton("Abrir carpeta")
        button.setProperty("variant", "primary")
        button.setFixedWidth(160)
        button.clicked.connect(self.open_requested.emit)
        layout.addStretch(1)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return box


def _thumbnail(record: ImageRecord) -> QPixmap:
    if record.thumb_path:
        pixmap = QPixmap(record.thumb_path)
        if not pixmap.isNull():
            return pixmap.scaled(
                186,
                132,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    pixmap = QPixmap(186, 132)
    pixmap.fill(QColor("#2a303b"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#c4bdb0"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, record.extension.upper() or "IMG")
    painter.end()
    return pixmap
