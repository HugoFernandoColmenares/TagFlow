"""Ventana principal de PyLens."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFontMetrics, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pylens import __version__
from pylens.core.analytics import summarize
from pylens.core.database import Database
from pylens.core.duplicates import group_by_exact, group_by_name, group_by_phash
from pylens.core.errors import UserError
from pylens.core.models import DuplicateGroup, ImageRecord, LibraryStats
from pylens.core.scanner import extract_metadata, refresh_thumbnail
from pylens.ui.components.dialogs import DuplicateDialog, ErrorDialog
from pylens.ui.components.filter_bar import FilterBar
from pylens.ui.components.gallery import Gallery
from pylens.ui.components.inspector import Inspector
from pylens.ui.components.stats_panel import StatsPanel
from pylens.ui.workers import DuplicateWorker, ScanWorker
from pylens.utils.config import Settings, asset_path, load_settings
from pylens.utils.files import (
    delete_file,
    group_files,
    move_file,
    optimize_image,
    rename_file,
    sanitize_filename,
    zip_files,
)
from pylens.utils.logging import setup_logging
from pylens.utils.text import QUALITY_ORDER, format_bytes

logger = logging.getLogger(__name__)


class _Mark(QWidget):
    """Marca pequeña del objetivo, dibujada para no depender de un archivo."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(38, 38)

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e8a54b"))
        painter.drawEllipse(1, 1, 36, 36)
        painter.setBrush(QColor("#171a21"))
        painter.drawEllipse(9, 9, 20, 20)
        painter.setBrush(QColor("#e8a54b"))
        painter.drawEllipse(16, 16, 6, 6)
        painter.setPen(QPen(QColor("#e8a54b"), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(5, 5, 28, 28)


class MainWindow(QMainWindow):
    """Organiza una carpeta local: índice, filtros, etiquetas y duplicados."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or load_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.thumb_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(self.settings.log_path, self.settings.log_level)
        self.db = Database(self.settings.db_path)
        self.db.initialize()
        self.scan_root: Path | None = None
        self._worker: ScanWorker | None = None
        self._hash_worker: DuplicateWorker | None = None
        self._seen: set[str] = set()
        self._scan_problems = 0
        self._busy = False
        self._refreshing = False
        self._show_dialog = True
        self._action_buttons: list[QPushButton] = []
        self.setWindowTitle("PyLens")
        self.resize(1360, 920)
        self.setMinimumSize(1100, 700)
        self._build()
        self._apply_icon()
        self._restore_last_folder()

    def is_busy(self) -> bool:
        scanning = self._worker is not None and self._worker.isRunning()
        hashing = self._hash_worker is not None and self._hash_worker.isRunning()
        return self._busy or scanning or hashing

    def image_count(self) -> int:
        return self.gallery.image_count()

    def load_folder(self, folder: Path) -> None:
        """Indexa `folder` en un hilo y vuelca el resultado al índice local."""

        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            raise UserError("Elige una carpeta válida.")
        self._detach("_worker")
        self._detach("_hash_worker")
        self.scan_root = folder
        self.db.set_setting("last_folder", str(folder))
        self._seen = set()
        self._scan_problems = 0
        self._show_path(str(folder))
        self._set_busy(True)
        self.status_label.setText("Preparando análisis…")
        worker = ScanWorker(folder, self.settings.thumb_dir, self.settings.thumb_size)
        self._worker = worker
        worker.image_found.connect(self._on_image)
        worker.problem.connect(self._on_problem)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_scan_finished)
        worker.start()

    def refresh_view(self) -> None:
        """Relee el índice con los filtros actuales. No toca el disco."""

        if self._refreshing:
            return
        self._refreshing = True
        try:
            if self.scan_root is None:
                self.gallery.set_images([])
                self.stats.set_stats(LibraryStats(qualities={tier: 0 for tier in QUALITY_ORDER}))
                self._show_overview(LibraryStats())
                self.filters.set_available_tags([])
                self.inspector.clear()
                self.count_label.setText("0 visibles")
                self._refresh_error_button()
                return
            root = str(self.scan_root)
            records = self.db.query_images(
                root,
                quality=self.filters.quality_value(),
                weight=self.filters.weight_value(),
                tags=self.filters.selected_tags(),
                text=self.filters.text_value(),
            )
            total = len(self.db.list_root(root))
            stats = summarize(records)
            self.filters.set_available_tags(self.db.distinct_tags(root))
            self.stats.set_stats(stats)
            self._show_overview(stats)
            self.gallery.set_images(records)
            self.count_label.setText(f"{len(records)} visibles de {total}")
            self._refresh_error_button()
        finally:
            self._refreshing = False

    def rename_selected(self, new_name: str) -> None:
        self._ensure_idle()
        records = self._batch()
        if len(records) != 1:
            raise UserError("Renombra una imagen a la vez.")
        record = records[0]
        target = rename_file(Path(record.path), new_name)
        self._remember_move(record, target)
        self.refresh_view()

    def move_selected(self, destination: Path) -> None:
        self._ensure_idle()
        for record in self._batch():
            target = move_file(Path(record.path), destination)
            self._remember_move(record, target)
        self.refresh_view()

    def delete_selected(self) -> None:
        self._ensure_idle()
        self.delete_ids([record.id for record in self._batch() if record.id is not None])

    def delete_ids(self, image_ids: list[int]) -> None:
        for image_id in image_ids:
            record = self.db.get_by_id(image_id)
            if record is None:
                continue
            delete_file(Path(record.path))
            if record.thumb_path:
                Path(record.thumb_path).unlink(missing_ok=True)
            self.db.delete_image(image_id)
        self.refresh_view()

    def group_selected(self, folder_name: str) -> Path:
        self._ensure_idle()
        if self.scan_root is None:
            raise UserError("Primero abre una carpeta.")
        records = self._batch()
        destination = self.scan_root / sanitize_filename(folder_name)
        moved = group_files([Path(record.path) for record in records], destination)
        mapping = {str(src.resolve()).casefold(): target.resolve() for src, target in moved}
        for record in records:
            target = mapping.get(str(Path(record.path).resolve()).casefold())
            if target is not None:
                self._remember_move(record, target)
        self.refresh_view()
        return destination

    def zip_selected(self, archive: Path) -> Path:
        self._ensure_idle()
        return zip_files(
            [Path(record.path) for record in self._batch()],
            archive,
            base=self.scan_root,
        )

    def optimize_selected(self, quality: int) -> tuple[int, int]:
        self._ensure_idle()
        if self.scan_root is None:
            raise UserError("Primero abre una carpeta.")
        before_total = 0
        after_total = 0
        for record in self._batch():
            if record.id is None:
                continue
            before, after = optimize_image(Path(record.path), quality)
            before_total += before
            after_total += after
            updated = extract_metadata(
                Path(record.path),
                self.scan_root,
                self.settings.thumb_dir,
                self.settings.thumb_size,
            )
            if record.thumb_path and record.thumb_path != updated.thumb_path:
                Path(record.thumb_path).unlink(missing_ok=True)
            self.db.update_technical(record.id, updated)
        self.refresh_view()
        return before_total, after_total

    def find_duplicates(self, show_dialog: bool = True) -> None:
        """Compara nombres al momento y, si se pidió, hashes en segundo plano."""

        self._ensure_idle()
        if self.scan_root is None:
            raise UserError("Primero abre una carpeta.")
        self._show_dialog = show_dialog
        exact = self.exact_check.isChecked()
        visual = self.visual_check.isChecked()
        pending = [
            record
            for record in self.db.list_root(str(self.scan_root))
            if record.id is not None
            and ((exact and not record.md5) or (visual and not record.phash))
        ]
        if not pending:
            self._present_duplicates()
            return
        self._set_busy(True)
        self.status_label.setText("Comparando imágenes…")
        worker = DuplicateWorker(pending, exact, visual)
        self._hash_worker = worker
        worker.hashed.connect(self._on_hashed)
        worker.problem.connect(self._on_problem)
        worker.progress.connect(self._on_hash_progress)
        worker.finished.connect(self._on_hash_finished)
        worker.start()

    def collect_groups(self) -> list[DuplicateGroup]:
        if self.scan_root is None:
            return []
        records = self.db.list_root(str(self.scan_root))
        groups = group_by_name(records)
        if self.exact_check.isChecked():
            groups.extend(group_by_exact(records))
        if self.visual_check.isChecked():
            groups.extend(group_by_phash(records))
        return groups

    def build_duplicate_dialog(self) -> DuplicateDialog | None:
        groups = self.collect_groups()
        if not groups or self.scan_root is None:
            return None
        records = {
            record.id: record
            for record in self.db.list_root(str(self.scan_root))
            if record.id is not None
        }
        return DuplicateDialog(groups, records, self)

    def show_errors(self) -> None:
        ErrorDialog(self.db.list_errors(), self).exec()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._detach("_worker")
        self._detach("_hash_worker")
        self.db.close()
        super().closeEvent(event)

    def _build(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setContentsMargins(14, 14, 14, 14)
        body.setSpacing(14)
        body.addWidget(self._build_sidebar(), 0)
        body.addWidget(self._build_center(), 1)
        body.addWidget(self._build_inspector(), 0)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self._build_menu()

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Header")
        frame.setFixedHeight(78)
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 10, 16, 10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("PyLens")
        title.setObjectName("Title")
        subtitle = QLabel("Índice local de imágenes")
        subtitle.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        self.status_label = QLabel("Listo")
        self.status_label.setObjectName("Muted")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.hide()
        self.errors_button = QPushButton("Registro")
        self.errors_button.setProperty("variant", "ghost")
        self.errors_button.clicked.connect(self.show_errors)
        row.addWidget(_Mark())
        row.addLayout(titles)
        row.addStretch(1)
        row.addWidget(self.status_label)
        row.addWidget(self.progress)
        row.addWidget(self.errors_button)
        return frame

    def _build_sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(330)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)
        folder = QWidget()
        folder_layout = QVBoxLayout(folder)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.open_button = QPushButton("Abrir carpeta")
        self.open_button.setProperty("variant", "primary")
        self.open_button.clicked.connect(self._choose_folder)
        self.rescan_button = QPushButton("Volver a indexar")
        self.rescan_button.clicked.connect(self._rescan)
        self.path_label = QLabel("Ninguna carpeta abierta")
        self.path_label.setObjectName("Muted")
        folder_layout.addWidget(self.open_button)
        folder_layout.addWidget(self.rescan_button)
        folder_layout.addWidget(self.path_label)
        self.filters = FilterBar()
        self.filters.changed.connect(self.refresh_view)
        duplicates = QWidget()
        dup_layout = QVBoxLayout(duplicates)
        dup_layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel("El nombre de las copias se compara siempre.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.exact_check = QCheckBox("Bytes idénticos (MD5 / SHA-256)")
        self.visual_check = QCheckBox("Aspecto similar (pHash)")
        self.duplicate_button = QPushButton("Buscar duplicados")
        self.duplicate_button.clicked.connect(lambda: self._run(lambda: self.find_duplicates(True)))
        dup_layout.addWidget(note)
        dup_layout.addWidget(self.exact_check)
        dup_layout.addWidget(self.visual_check)
        dup_layout.addWidget(self.duplicate_button)
        self.stats = StatsPanel()
        layout.addWidget(self._card("Carpeta", folder))
        layout.addWidget(self._card("Filtros", self.filters))
        layout.addWidget(self._card("Duplicados", duplicates))
        layout.addWidget(self._card("Estadísticas", self.stats))
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _build_center(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.count_label = QLabel("0 visibles")
        self.count_label.setObjectName("Muted")
        self.overview = QLabel("")
        self.overview.setObjectName("Muted")
        self.overview.setWordWrap(True)
        mark = QPushButton("Marcar visibles")
        mark.setProperty("variant", "ghost")
        mark.clicked.connect(self._mark_visible)
        clear = QPushButton("Limpiar marcas")
        clear.setProperty("variant", "ghost")
        clear.clicked.connect(self._clear_marks)
        top.addWidget(self.count_label)
        top.addStretch(1)
        top.addWidget(mark)
        top.addWidget(clear)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for text, slot, variant in (
            ("Renombrar", self._prompt_rename, ""),
            ("Mover", self._prompt_move, ""),
            ("Agrupar", self._prompt_group, ""),
            ("Comprimir", self._prompt_zip, ""),
            ("Optimizar", self._prompt_optimize, ""),
            ("Eliminar", self._confirm_delete, "danger"),
        ):
            button = QPushButton(text)
            if variant:
                button.setProperty("variant", variant)
            button.clicked.connect(slot)
            self._action_buttons.append(button)
            actions.addWidget(button)
        self.gallery = Gallery()
        self.gallery.selection_changed.connect(self._on_selection)
        self.gallery.open_requested.connect(self._choose_folder)
        layout.addLayout(top)
        layout.addWidget(self.overview)
        layout.addLayout(actions)
        layout.addWidget(self.gallery, 1)
        return wrap

    def _build_inspector(self) -> QWidget:
        self.inspector = Inspector()
        self.inspector.tags_changed.connect(self._on_tags)
        frame = self._card("Imagen", self.inspector)
        frame.setFixedWidth(340)
        return frame

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        open_action = QAction("Abrir carpeta", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._choose_folder)
        rescan_action = QAction("Volver a indexar", self)
        rescan_action.setShortcut(QKeySequence("F5"))
        rescan_action.triggered.connect(self._rescan)
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(rescan_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        tools = self.menuBar().addMenu("Herramientas")
        duplicates = QAction("Buscar duplicados", self)
        duplicates.triggered.connect(lambda: self._run(lambda: self.find_duplicates(True)))
        ledger = QAction("Registro de errores", self)
        ledger.triggered.connect(self.show_errors)
        tools.addAction(duplicates)
        tools.addAction(ledger)
        help_menu = self.menuBar().addMenu("Ayuda")
        about = QAction("Acerca de PyLens", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _card(self, title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QLabel(title.upper())
        heading.setObjectName("Section")
        layout.addWidget(heading)
        layout.addWidget(content)
        return frame

    def _restore_last_folder(self) -> None:
        raw = self.db.get_setting("last_folder")
        if not raw or not Path(raw).is_dir():
            self.refresh_view()
            self._show_path(None)
            self.status_label.setText("Abre una carpeta para empezar")
            self._sync_buttons()
            return
        self.scan_root = Path(raw).resolve()
        self._show_path(str(self.scan_root))
        self.refresh_view()
        count = self.image_count()
        if count:
            self.status_label.setText(
                f"Índice guardado · {count} imágenes. Vuelve a indexar si la carpeta cambió."
            )
        else:
            self.status_label.setText("Esta carpeta todavía no está indexada.")
        self._sync_buttons()

    def _choose_folder(self) -> None:
        start = str(self.scan_root or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Elegir carpeta", start)
        if not chosen:
            return
        self._run(lambda: self.load_folder(Path(chosen)))

    def _rescan(self) -> None:
        if self.scan_root is None:
            self._choose_folder()
            return
        self._run(lambda: self.load_folder(self.scan_root))

    def _on_image(self, record: ImageRecord) -> None:
        if self.sender() is not self._worker:
            return
        try:
            stored = self.db.upsert_image(record)
        except Exception as exc:
            logger.exception("No pude guardar %s", record.path)
            self.db.log_error(f"No pude guardar {record.filename}: {exc}", path=record.path)
            return
        self._seen.add(stored.path)
        if len(self._seen) % 20 == 0:
            self.refresh_view()

    def _on_problem(self, path: str, message: str) -> None:
        sender = self.sender()
        if sender not in {self._worker, self._hash_worker}:
            return
        if sender is self._worker:
            self._scan_problems += 1
        try:
            self.db.log_error(message, path=path or None)
        except Exception:
            logger.exception("No pude anotar el error")
        self._refresh_error_button()

    def _on_progress(self, current: int, total: int) -> None:
        if self.sender() is not self._worker:
            return
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)
        self.status_label.setText(f"Indexando {current} de {total}")

    def _on_scan_finished(self) -> None:
        worker = self.sender()
        if worker is not self._worker or not isinstance(worker, ScanWorker):
            return
        removed = 0
        if not worker.cancelled and self.scan_root is not None:
            removed = self.db.prune(str(self.scan_root), self._seen)
        self._set_busy(False)
        self.refresh_view()
        if worker.cancelled:
            self.status_label.setText("Análisis cancelado")
            return
        unread = f" · {self._scan_problems} no leídas" if self._scan_problems else ""
        dropped = f" · {removed} fuera del disco" if removed else ""
        self.status_label.setText(f"{len(self._seen)} imágenes indexadas{unread}{dropped}")

    def _on_hashed(self, image_id: int, md5: str, sha256: str, phash: str) -> None:
        if self.sender() is not self._hash_worker:
            return
        self.db.update_hashes(
            image_id,
            md5=md5 or None,
            sha256=sha256 or None,
            phash=phash or None,
            exact=bool(md5),
            perceptual=bool(phash),
        )

    def _on_hash_progress(self, current: int, total: int) -> None:
        if self.sender() is not self._hash_worker:
            return
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)
        self.status_label.setText(f"Comparando {current} de {total}")

    def _on_hash_finished(self) -> None:
        if self.sender() is not self._hash_worker:
            return
        self._set_busy(False)
        self.refresh_view()
        self.status_label.setText("Comparación terminada")
        self._present_duplicates()

    def _present_duplicates(self) -> None:
        if not self._show_dialog:
            return
        dialog = self.build_duplicate_dialog()
        if dialog is None:
            if self._show_dialog:
                QMessageBox.information(
                    self,
                    "Duplicados",
                    "No encontré duplicados con estos criterios.",
                )
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        image_ids = dialog.selected_ids()
        if not image_ids:
            QMessageBox.information(self, "Duplicados", "No marcaste copias para eliminar.")
            return
        self.delete_ids(image_ids)

    def _on_selection(self, record: ImageRecord | None) -> None:
        if self._refreshing:
            record = self.gallery.selected()
        if record is None or record.id is None:
            self.inspector.clear()
            return
        fresh = self.db.get_by_id(record.id)
        self.inspector.show_record(fresh) if fresh is not None else self.inspector.clear()

    def _on_tags(self, tags: list[str]) -> None:
        record = self.inspector.record
        if record is None or record.id is None:
            return
        try:
            self.db.update_tags(record.id, tags)
        except UserError as exc:
            QMessageBox.warning(self, "PyLens", str(exc))
            return
        self.refresh_view()

    def _prompt_rename(self) -> None:
        try:
            records = self._batch()
        except UserError as exc:
            QMessageBox.information(self, "PyLens", str(exc))
            return
        if len(records) != 1:
            QMessageBox.information(self, "PyLens", "Selecciona una sola imagen para renombrarla.")
            return
        name, accepted = QInputDialog.getText(
            self,
            "Renombrar",
            "Nuevo nombre",
            text=Path(records[0].filename).stem,
        )
        if accepted:
            self._run(lambda: self.rename_selected(name))

    def _prompt_move(self) -> None:
        start = str(self.scan_root or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Mover a…", start)
        if chosen:
            self._run(lambda: self.move_selected(Path(chosen)))

    def _prompt_group(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Agrupar",
            "Nombre de la carpeta",
            text="seleccion",
        )
        if accepted:
            self._run(lambda: self.group_selected(name))

    def _prompt_zip(self) -> None:
        start = str((self.scan_root or Path.home()) / "imagenes.zip")
        chosen, _selected = QFileDialog.getSaveFileName(self, "Crear zip", start, "Zip (*.zip)")
        if not chosen:
            return
        if not chosen.lower().endswith(".zip"):
            chosen += ".zip"

        def action() -> None:
            archive = self.zip_selected(Path(chosen))
            QMessageBox.information(self, "PyLens", f"Archivo creado:\n{archive}")

        self._run(action)

    def _prompt_optimize(self) -> None:
        quality, accepted = QInputDialog.getInt(
            self,
            "Optimizar",
            "Calidad para JPEG y WebP. El PNG se optimiza sin cambiar de formato.",
            85,
            40,
            95,
        )
        if not accepted:
            return

        def action() -> None:
            before, after = self.optimize_selected(quality)
            QMessageBox.information(
                self,
                "PyLens",
                f"Peso anterior: {before} bytes\nPeso nuevo: {after} bytes",
            )

        self._run(action)

    def _confirm_delete(self) -> None:
        try:
            records = self._batch()
        except UserError as exc:
            QMessageBox.information(self, "PyLens", str(exc))
            return
        preview = "\n".join(record.filename for record in records[:8])
        extra = "" if len(records) <= 8 else f"\n… y {len(records) - 8} más"
        answer = QMessageBox.question(
            self,
            "Eliminar imágenes",
            f"Se eliminarán del disco y del índice:\n\n{preview}{extra}",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run(self.delete_selected)

    def _mark_visible(self) -> None:
        self.gallery.mark_visible()

    def _clear_marks(self) -> None:
        self.gallery.clear_marks()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "PyLens",
            f"PyLens {__version__}\n\n"
            "Organiza, etiqueta y depura imágenes sin salir de este equipo.\n"
            "Nada se envía a un servidor.",
        )

    def _remember_move(self, record: ImageRecord, new_path: Path) -> None:
        old = Path(record.path)
        new_path = new_path.resolve()
        try:
            self._update_location(record, new_path)
        except Exception:
            if new_path.exists() and not old.exists():
                try:
                    shutil.move(str(new_path), str(old))
                except OSError:
                    logger.exception("No pude deshacer el movimiento de %s", new_path)
            raise

    def _update_location(self, record: ImageRecord, new_path: Path) -> None:
        if record.id is None:
            raise UserError("La imagen no está en el índice.")
        new_path = new_path.resolve()
        stat = new_path.stat()
        thumb: str | None = None
        try:
            thumb = refresh_thumbnail(new_path, self.settings.thumb_dir, self.settings.thumb_size)
        except Exception:
            logger.exception("No pude regenerar la miniatura de %s", new_path)
        if record.thumb_path and record.thumb_path != thumb:
            Path(record.thumb_path).unlink(missing_ok=True)
        try:
            self.db.relocate(record.id, new_path, thumb, stat.st_mtime_ns)
        except sqlite3.IntegrityError as exc:
            raise UserError("Esa ruta ya está en el índice.") from exc

    def _batch(self) -> list[ImageRecord]:
        records = self.gallery.batch()
        if not records:
            raise UserError("Selecciona al menos una imagen.")
        return records

    def _ensure_idle(self) -> None:
        if self._busy:
            raise UserError("Espera a que termine el análisis.")

    def _detach(self, name: str) -> None:
        worker = getattr(self, name)
        if worker is None:
            return
        worker.cancel()
        setattr(self, name, None)
        if worker.isRunning():
            worker.wait(5000)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        for button in self._action_buttons:
            button.setEnabled(not busy)
        self._sync_buttons()

    def _show_path(self, path: str | None) -> None:
        if not path:
            self.path_label.setText("Ninguna carpeta abierta")
            self.path_label.setToolTip("")
            return
        self.path_label.setToolTip(path)
        metrics = QFontMetrics(self.path_label.font())
        self.path_label.setText(metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 280))

    def _show_overview(self, stats: LibraryStats) -> None:
        if stats.count == 0:
            self.overview.setText("")
            return
        depth = "sin subcarpetas" if stats.max_depth == 0 else f"{stats.max_depth} niveles"
        dominant = stats.dominant_format or "—"
        self.overview.setText(
            f"{format_bytes(stats.total_bytes)} en disco · "
            f"promedio {format_bytes(round(stats.average_bytes))} · "
            f"{depth} · {dominant}"
        )

    def _sync_buttons(self) -> None:
        ready = self.scan_root is not None and not self._busy
        self.rescan_button.setEnabled(ready)
        self.duplicate_button.setEnabled(ready)

    def _refresh_error_button(self) -> None:
        count = self.db.count_errors()
        self.errors_button.setText("Registro" if count == 0 else f"Registro ({count})")

    def _run(self, action) -> None:  # type: ignore[no-untyped-def]
        try:
            action()
        except UserError as exc:
            QMessageBox.warning(self, "PyLens", str(exc))
        except Exception as exc:
            logger.exception("Operación fallida")
            try:
                self.db.log_error(str(exc))
            except Exception:
                logger.exception("No pude anotar el error")
            QMessageBox.critical(
                self,
                "PyLens",
                "No pude completar la operación. El detalle quedó en el registro de errores.",
            )
            self._refresh_error_button()

    def _apply_icon(self) -> None:
        icon = asset_path("icon.png")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
