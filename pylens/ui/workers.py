"""Hilos de análisis y de comparación. No tocan la base de datos."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from pylens.core.duplicates import hash_file, perceptual_hash
from pylens.core.errors import ScanError, UserError
from pylens.core.models import ImageRecord
from pylens.core.scanner import discover_images, extract_metadata


class ScanWorker(QThread):
    """Recorre una carpeta y emite un registro por imagen legible."""

    progress = Signal(int, int)
    image_found = Signal(object)
    problem = Signal(str, str)

    def __init__(self, root: Path, thumb_dir: Path, thumb_size: int) -> None:
        super().__init__()
        self.root = root
        self.thumb_dir = thumb_dir
        self.thumb_size = thumb_size
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def run(self) -> None:
        try:
            files, issues = discover_images(self.root, skip_dir=self.thumb_dir)
        except ScanError as exc:
            self.problem.emit(exc.path, exc.message)
            return
        except Exception as exc:
            self.problem.emit(str(self.root), f"No pude recorrer la carpeta: {exc}")
            return
        for path, message in issues:
            self.problem.emit(path, message)
        total = len(files)
        self.progress.emit(0, total)
        for index, path in enumerate(files, start=1):
            if self._cancel:
                return
            try:
                record = extract_metadata(path, self.root, self.thumb_dir, self.thumb_size)
            except ScanError as exc:
                self.problem.emit(exc.path, exc.message)
            except Exception as exc:
                self.problem.emit(str(path), f"Error inesperado: {exc}")
            else:
                self.image_found.emit(record)
            self.progress.emit(index, total)


class DuplicateWorker(QThread):
    """Calcula MD5, SHA-256 y pHash de las imágenes que todavía no los tienen."""

    progress = Signal(int, int)
    hashed = Signal(int, str, str, str)
    problem = Signal(str, str)

    def __init__(self, records: list[ImageRecord], exact: bool, perceptual: bool) -> None:
        super().__init__()
        self.records = records
        self.exact = exact
        self.perceptual = perceptual
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self.records)
        self.progress.emit(0, total)
        for index, record in enumerate(self.records, start=1):
            if self._cancel:
                return
            if record.id is None:
                self.progress.emit(index, total)
                continue
            md5 = ""
            sha256 = ""
            phash = ""
            try:
                if self.exact and not record.md5:
                    md5, sha256 = hash_file(Path(record.path))
                if self.perceptual and not record.phash:
                    phash = perceptual_hash(Path(record.path)) or ""
            except UserError as exc:
                self.problem.emit(record.path, str(exc))
            except Exception as exc:
                self.problem.emit(record.path, f"No pude comparar {record.filename}: {exc}")
            else:
                if md5 or phash:
                    self.hashed.emit(record.id, md5, sha256, phash)
            self.progress.emit(index, total)
