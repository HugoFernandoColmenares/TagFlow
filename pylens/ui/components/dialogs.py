"""Diálogos de duplicados y del registro de errores."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pylens.core.models import DuplicateGroup, ErrorEntry, ImageRecord
from pylens.utils.text import format_bytes

_KIND = {"name": "Nombre", "md5": "Bytes", "phash": "Aspecto"}


class DuplicateDialog(QDialog):
    """Lista grupos y deja marcar las copias que se van a quitar."""

    def __init__(
        self,
        groups: list[DuplicateGroup],
        records: dict[int, ImageRecord],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicados")
        self.resize(820, 640)
        self._boxes: list[tuple[int, QCheckBox]] = []
        root = QVBoxLayout(self)
        intro = QLabel(
            f"{len(groups)} grupos. La copia de mayor peso queda desmarcada para conservarla."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        body = QVBoxLayout(host)
        body.setSpacing(12)
        for group in groups:
            body.addWidget(self._group_card(group, records))
        body.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        remove = QPushButton("Eliminar marcados")
        remove.setProperty("variant", "danger")
        remove.clicked.connect(self.accept)
        buttons.addWidget(close)
        buttons.addWidget(remove)
        root.addLayout(buttons)

    def selected_ids(self) -> list[int]:
        chosen: list[int] = []
        seen: set[int] = set()
        for image_id, box in self._boxes:
            if box.isChecked() and image_id not in seen:
                seen.add(image_id)
                chosen.append(image_id)
        return chosen

    def _group_card(self, group: DuplicateGroup, records: dict[int, ImageRecord]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        title = QLabel(f"{_KIND.get(group.kind, group.kind)}  ·  {group.title}")
        title.setWordWrap(True)
        detail = QLabel(group.detail)
        detail.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(detail)
        members = [records[image_id] for image_id in group.image_ids if image_id in records]
        keeper = max(members, key=lambda record: (record.size_bytes, -len(record.filename))) if members else None
        for record in members:
            if record.id is None:
                continue
            box = QCheckBox(
                f"{record.filename}   ·   {format_bytes(record.size_bytes)}   ·   "
                f"{record.width}×{record.height}"
            )
            box.setChecked(keeper is None or record.id != keeper.id)
            box.toggled.connect(
                lambda checked, image_id=record.id, source=box: self._sync(image_id, checked, source)
            )
            self._boxes.append((record.id, box))
            layout.addWidget(box)
        return frame

    def _sync(self, image_id: int, checked: bool, source: QCheckBox) -> None:
        for other_id, other in self._boxes:
            if other_id == image_id and other is not source:
                other.blockSignals(True)
                other.setChecked(checked)
                other.blockSignals(False)


class ErrorDialog(QDialog):
    """Muestra el libro de errores local."""

    def __init__(self, entries: list[ErrorEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Registro de errores")
        self.resize(720, 360)
        root = QVBoxLayout(self)
        if not entries:
            empty = QLabel("No hay errores registrados.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            host = QWidget()
            body = QVBoxLayout(host)
            for entry in entries:
                frame = QFrame()
                frame.setObjectName("Card")
                layout = QVBoxLayout(frame)
                when = entry.created_at.replace("T", " ").replace("+00:00", " UTC")
                heading = QLabel(when)
                heading.setObjectName("Muted")
                location = QLabel(entry.path or "General")
                location.setWordWrap(True)
                message = QLabel(entry.message)
                message.setWordWrap(True)
                layout.addWidget(heading)
                layout.addWidget(location)
                layout.addWidget(message)
                body.addWidget(frame)
            body.addStretch(1)
            scroll.setWidget(host)
            root.addWidget(scroll, 1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
