"""Selector de carpetas y archivos integrado en la interfaz de TagFlow."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tagflow.core.errors import UserError
from tagflow.utils.files import sanitize_filename


class FolderPickerDialog(QDialog):
    """Explorador propio: evita el diálogo nativo y mantiene el estilo de la app."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "Elegir carpeta",
        start: Path | None = None,
        accept_text: str = "Seleccionar",
        hint: str = "",
        file_name: str | None = None,
        file_suffix: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 560)
        self._file_suffix = file_suffix
        self._folder = Path.home()
        self._file_mode = file_name is not None

        root = QVBoxLayout(self)
        root.setSpacing(10)
        if hint:
            explanation = QLabel(hint)
            explanation.setObjectName("Muted")
            explanation.setWordWrap(True)
            root.addWidget(explanation)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Escribe o pega una ruta")
        self.path_edit.returnPressed.connect(self._go)
        go = QPushButton("Ir")
        go.clicked.connect(self._go)
        up = QPushButton("Subir")
        up.clicked.connect(self._up)
        home = QPushButton("Inicio")
        home.clicked.connect(lambda: self.navigate_to(Path.home()))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(go)
        path_row.addWidget(up)
        path_row.addWidget(home)
        root.addLayout(path_row)

        self.drives = QComboBox()
        self.drives.setVisible(os.name == "nt")
        if os.name == "nt":
            for drive in QDir.drives():
                self.drives.addItem(drive.absolutePath())
            self.drives.currentTextChanged.connect(self._on_drive)
            root.addWidget(self.drives)

        self.list = QListWidget()
        self.list.setToolTip("Doble clic o Enter para entrar en una carpeta.")
        self.list.itemActivated.connect(self._on_item_activated)
        root.addWidget(self.list, 1)

        new_row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Nombre de la nueva carpeta")
        self.new_name.returnPressed.connect(self._create_from_input)
        create = QPushButton("Nueva carpeta")
        create.clicked.connect(self._create_from_input)
        new_row.addWidget(self.new_name, 1)
        new_row.addWidget(create)
        root.addLayout(new_row)

        self.file_edit: QLineEdit | None = None
        if self._file_mode:
            file_row = QHBoxLayout()
            file_row.addWidget(QLabel("Nombre del archivo"))
            self.file_edit = QLineEdit(file_name)
            self.file_edit.returnPressed.connect(self._accept)
            self.file_edit.textChanged.connect(lambda _text: self._update_destination())
            file_row.addWidget(self.file_edit, 1)
            root.addLayout(file_row)

        self.error = QLabel("")
        self.error.setObjectName("FormError")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

        footer = QHBoxLayout()
        self.destination = QLabel("")
        self.destination.setObjectName("Muted")
        self.destination.setWordWrap(True)
        footer.addWidget(self.destination, 1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        accept = QPushButton(accept_text)
        accept.setProperty("variant", "primary")
        accept.clicked.connect(self._accept)
        footer.addWidget(cancel)
        footer.addWidget(accept)
        root.addLayout(footer)

        self.navigate_to(start or Path.home())

    def current_folder(self) -> Path:
        return self._folder

    def selected_folder(self) -> Path:
        return self._folder

    def selected_path(self) -> Path:
        return self._folder if self.file_edit is None else self._folder / self._file_name()

    def navigate_to(self, path: Path) -> None:
        try:
            target = Path(os.path.expandvars(str(path))).expanduser().resolve()
        except OSError as exc:
            self._show_error(f"No pude abrir esa ruta: {exc}")
            return
        if not target.is_dir():
            self._show_error("Esa carpeta no existe.")
            return
        self._folder = target
        self.path_edit.setText(str(target))
        self._hide_error()
        self._refresh_list()
        self._update_destination()
        self._sync_drives()

    def create_folder(self, name: str) -> Path:
        """Crea una carpeta dentro de la actual y entra en ella."""

        cleaned = sanitize_filename(name)
        target = self._folder / cleaned
        if target.exists():
            raise UserError("Ya existe una carpeta con ese nombre.")
        try:
            target.mkdir()
        except OSError as exc:
            raise UserError(f"No pude crear la carpeta: {exc.strerror or exc}") from exc
        self.navigate_to(target)
        return target

    def set_file_name(self, name: str) -> None:
        if self.file_edit is not None:
            self.file_edit.setText(name)

    def _refresh_list(self) -> None:
        self.list.clear()
        if self._folder.parent != self._folder:
            parent = QListWidgetItem("..   Subir un nivel")
            parent.setData(Qt.ItemDataRole.UserRole, str(self._folder.parent))
            parent.setForeground(QColor("#8b93a3"))
            self.list.addItem(parent)
        entries: list[Path] = []
        try:
            for entry in self._folder.iterdir():
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        entries.append(entry)
                except OSError:
                    continue
        except OSError as exc:
            self._show_error(f"No pude leer la carpeta: {exc.strerror or exc}")
        entries.sort(key=lambda entry: entry.name.casefold())
        for entry in entries:
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, str(entry))
            self.list.addItem(item)
        if not entries:
            empty = QListWidgetItem("Sin subcarpetas")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QColor("#8b93a3"))
            self.list.addItem(empty)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        target = item.data(Qt.ItemDataRole.UserRole)
        if target:
            self.navigate_to(Path(str(target)))

    def _on_drive(self, drive: str) -> None:
        if drive:
            self.navigate_to(Path(drive))

    def _sync_drives(self) -> None:
        if os.name != "nt":
            return
        anchor = str(Path(self._folder.anchor))
        index = next(
            (
                position
                for position in range(self.drives.count())
                if str(Path(self.drives.itemText(position))) == anchor
            ),
            -1,
        )
        if index >= 0 and index != self.drives.currentIndex():
            self.drives.blockSignals(True)
            self.drives.setCurrentIndex(index)
            self.drives.blockSignals(False)

    def _go(self) -> None:
        raw = self.path_edit.text().strip()
        if not raw:
            return
        path = Path(os.path.expandvars(raw)).expanduser()
        if not path.is_absolute():
            path = self._folder / path
        if path.is_dir():
            self.navigate_to(path)
            return
        if self._file_mode and path.parent.is_dir():
            self.navigate_to(path.parent)
            self.set_file_name(path.name)
            return
        self._show_error("La carpeta no existe. Puedes crearla con «Nueva carpeta».")

    def _up(self) -> None:
        if self._folder.parent != self._folder:
            self.navigate_to(self._folder.parent)

    def _create_from_input(self) -> None:
        raw = self.new_name.text().strip()
        if not raw:
            self._show_error("Escribe un nombre para la carpeta.")
            return
        try:
            self.create_folder(raw)
        except UserError as exc:
            self._show_error(str(exc))
            return
        self.new_name.clear()

    def _file_name(self) -> str:
        raw = "" if self.file_edit is None else self.file_edit.text().strip()
        if not raw:
            raise UserError("Escribe un nombre para el archivo.")
        name = sanitize_filename(raw)
        if self._file_suffix and not name.lower().endswith(self._file_suffix.lower()):
            name = f"{name}{self._file_suffix}"
        return name

    def _accept(self) -> None:
        try:
            target = self.selected_path()
        except UserError as exc:
            self._show_error(str(exc))
            return
        if self._file_mode and target.exists():
            answer = QMessageBox.question(
                self,
                "Reemplazar archivo",
                f"Ya existe:\n{target.name}\n\n¿Quieres reemplazarlo?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def _update_destination(self) -> None:
        if self._file_mode:
            try:
                name = self._file_name()
            except UserError:
                name = "…"
            text = f"Se guardará en: {self._folder / name}"
        else:
            text = f"Destino: {self._folder}"
        self.destination.setText(text)
        self.destination.setToolTip(str(self._folder))

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()

    def _hide_error(self) -> None:
        self.error.clear()
        self.error.hide()
