"""Resumen estadístico de la vista filtrada."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from tagflow.core.models import LibraryStats
from tagflow.utils.text import QUALITY_ORDER, format_bytes, quality_label

_QUALITY_COLORS = {"4K": "#8eb4d4", "HD": "#7eb8a8", "Low-res": "#d7a15e"}


class StatsPanel(QWidget):
    """Cifras y barras de la selección visible."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.summary = QLabel("Todavía no hay imágenes en esta vista.")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.bars = QVBoxLayout()
        self.bars.setSpacing(6)
        layout.addWidget(self.summary)
        layout.addLayout(self.bars)

    def set_stats(self, stats: LibraryStats) -> None:
        self._clear()
        if stats.count == 0:
            self.summary.setText("Todavía no hay imágenes en esta vista.")
            return
        depth = (
            "Sin subcarpetas"
            if stats.max_depth == 0
            else f"{stats.max_depth} niveles de carpetas"
        )
        dominant = stats.dominant_format or "—"
        self.summary.setText(
            f"{stats.count} imágenes\n"
            f"{format_bytes(stats.total_bytes)} en disco\n"
            f"Promedio {format_bytes(round(stats.average_bytes))}\n"
            f"{depth}\n"
            f"Formato más común: {dominant}"
        )
        self._heading("Formatos")
        format_max = max((count for _, count in stats.formats), default=1)
        for name, count in stats.formats:
            self._bar(name, count, format_max, "#e8a54b")
        self._heading("Calidad")
        quality_max = max(stats.qualities.values(), default=1)
        for tier in QUALITY_ORDER:
            self._bar(
                quality_label(tier),
                stats.qualities.get(tier, 0),
                quality_max,
                _QUALITY_COLORS.get(tier, "#e8a54b"),
            )
        self._heading("Etiquetas")
        if not stats.tags:
            empty = QLabel("Todavía no hay etiquetas.")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.bars.addWidget(empty)
            return
        tag_max = stats.tags[0][1]
        for name, count in stats.tags[:6]:
            self._bar(name, count, tag_max, "#c9846a")

    def _heading(self, text: str) -> None:
        label = QLabel(text.upper())
        label.setObjectName("Section")
        self.bars.addWidget(label)

    def _bar(self, name: str, value: int, maximum: int, color: str) -> None:
        label = QLabel(f"{name}  ·  {value}")
        label.setObjectName("StatValue")
        bar = QProgressBar()
        bar.setRange(0, max(maximum, 1))
        bar.setValue(value)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            "QProgressBar { background: #2a303b; border: none; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )
        self.bars.addWidget(label)
        self.bars.addWidget(bar)

    def _clear(self) -> None:
        while self.bars.count():
            item = self.bars.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
