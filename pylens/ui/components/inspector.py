"""Vista previa, metadatos y etiquetas de la imagen activa."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pylens.core.models import ImageRecord
from pylens.ui.components.tag_manager import TagManager
from pylens.utils.text import format_bytes, quality_label


class Inspector(QWidget):
    """Panel derecho: foto, datos técnicos y etiquetas."""

    tags_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.record: ImageRecord | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.empty = QLabel("Selecciona una imagen para ver sus datos y etiquetas.")
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.tags = TagManager()
        self.tags.changed.connect(self.tags_changed.emit)
        layout.addWidget(self.empty)
        layout.addWidget(self.preview)
        layout.addWidget(self.meta)
        layout.addWidget(self.tags)
        layout.addStretch(1)
        self.clear()

    def clear(self) -> None:
        self.record = None
        self.empty.show()
        self.preview.hide()
        self.meta.hide()
        self.tags.hide()

    def show_record(self, record: ImageRecord) -> None:
        self.record = record
        self.empty.hide()
        self.preview.show()
        self.meta.show()
        self.tags.show()
        self.preview.setPixmap(_preview(record.path))
        lines = [
            record.filename,
            record.folder,
            f"{record.width}×{record.height} · {record.format} · {quality_label(record.quality_tier)}",
            f"{format_bytes(record.size_bytes)} · {record.bytes_per_pixel:.2f} B/px",
        ]
        if record.sharpness is None:
            lines.append("Nitidez no disponible")
        else:
            lines.append(f"Nitidez {record.sharpness:.0f}")
        if record.md5:
            lines.append(f"MD5 {record.md5}")
        if record.sha256:
            lines.append(f"SHA-256 {record.sha256[:20]}…")
        if record.phash:
            lines.append(f"pHash {record.phash}")
        self.meta.setText("\n".join(lines))
        self.tags.set_tags(record.tags)


def _preview(path: str) -> QPixmap:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        reader.setScaledSize(size.scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if not image.isNull():
        return QPixmap.fromImage(image)
    pixmap = QPixmap(320, 180)
    pixmap.fill(QColor("#2a303b"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#c4bdb0"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Sin vista previa")
    painter.end()
    return pixmap
