"""Hilos de análisis y de comparación. No tocan la base de datos."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from tagflow.core.duplicates import hash_file, perceptual_hash
from tagflow.core.errors import ScanError, UserError
from tagflow.core.models import ImageRecord
from tagflow.core.scanner import discover_images, extract_metadata

# Emisión por lotes: evita saturar el hilo de la interfaz con 14k señales.
_SCAN_BATCH = 40
_HASH_BATCH = 25
_PROGRESS_STEP = 25


class ScanWorker(QThread):
    """Recorre una carpeta y emite lotes de registros nuevos o modificados."""

    progress = Signal(int, int)
    batch_found = Signal(object)
    cached = Signal(object)
    problem = Signal(str, str)

    def __init__(
        self,
        root: Path,
        thumb_dir: Path,
        thumb_size: int,
        fingerprints: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        super().__init__()
        self.root = root
        self.thumb_dir = thumb_dir
        self.thumb_size = thumb_size
        self.fingerprints = fingerprints or {}
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
        pending: list[ImageRecord] = []
        cached: list[str] = []
        for index, path in enumerate(files, start=1):
            if self._cancel:
                break
            try:
                stat = path.stat()
            except OSError as exc:
                self.problem.emit(str(path), f"Sin permiso para leer: {exc.strerror or exc}")
                self._emit_progress(index, total)
                continue
            known = self.fingerprints.get(str(path))
            if known is not None and known[0] == stat.st_mtime_ns and known[1] == stat.st_size:
                cached.append(str(path))
                if len(cached) >= _SCAN_BATCH:
                    self.cached.emit(cached)
                    cached = []
                self._emit_progress(index, total)
                continue
            try:
                record = extract_metadata(
                    path,
                    self.root,
                    self.thumb_dir,
                    self.thumb_size,
                    measure_sharpness=False,
                )
            except ScanError as exc:
                self.problem.emit(exc.path, exc.message)
            except Exception as exc:
                self.problem.emit(str(path), f"Error inesperado: {exc}")
            else:
                pending.append(record)
                if len(pending) >= _SCAN_BATCH:
                    self.batch_found.emit(pending)
                    pending = []
            self._emit_progress(index, total)
        if pending and not self._cancel:
            self.batch_found.emit(pending)
        if cached and not self._cancel:
            self.cached.emit(cached)

    def _emit_progress(self, current: int, total: int) -> None:
        if current == total or current % _PROGRESS_STEP == 0 or current == 1:
            self.progress.emit(current, total)


class DuplicateWorker(QThread):
    """Calcula MD5, SHA-256 y pHash de las imágenes que todavía no los tienen."""

    progress = Signal(int, int)
    hashed_batch = Signal(object)
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
        batch: list[tuple[int, str, str, str]] = []
        for index, record in enumerate(self.records, start=1):
            if self._cancel:
                return
            if record.id is None:
                self._emit_progress(index, total)
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
                    batch.append((record.id, md5, sha256, phash))
                    if len(batch) >= _HASH_BATCH:
                        self.hashed_batch.emit(batch)
                        batch = []
            self._emit_progress(index, total)
        if batch and not self._cancel:
            self.hashed_batch.emit(batch)

    def _emit_progress(self, current: int, total: int) -> None:
        if current == total or current % _PROGRESS_STEP == 0 or current == 1:
            self.progress.emit(current, total)
