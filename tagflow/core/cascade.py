"""Agrupación por calidad en cascada: una subcarpeta tras otra, sin índice."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFile, UnidentifiedImageError

from tagflow.core.imaging import quality_tier
from tagflow.core.scanner import IMAGE_EXTENSIONS
from tagflow.utils.files import (
    ensure_directory,
    move_into_uniquified,
    resolve_subdir,
    seed_taken_names,
)
from tagflow.utils.text import QUALITY_LABELS, QUALITY_ORDER, quality_label

logger = logging.getLogger(__name__)

# Cabeceras a medias siguen sirviendo para clasificar sin tumbar el lote.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Nombres de destino que no deben procesarse como carpetas de cascada ni recorridos.
_QUALITY_DIR_NAMES = {label.casefold() for label in QUALITY_LABELS.values()}
_PROGRESS_EVERY = 100
_SIZE_WORKERS = min(16, max(4, (os.cpu_count() or 4) * 2))


@dataclass
class FolderCascadeResult:
    folder: Path
    moved: dict[str, int] = field(default_factory=dict)
    scanned: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def moved_total(self) -> int:
        return sum(self.moved.values())


@dataclass
class CascadeResult:
    base: Path
    folders: list[FolderCascadeResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def moved_total(self) -> int:
        return sum(item.moved_total for item in self.folders)

    @property
    def error_total(self) -> int:
        return sum(len(item.errors) for item in self.folders)


CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[int, int, str, int, int], None]
FolderCallback = Callable[[FolderCascadeResult], None]


def is_quality_dirname(name: str) -> bool:
    return name.casefold() in _QUALITY_DIR_NAMES


def list_cascade_targets(base: Path) -> list[Path]:
    """Subcarpetas inmediatas de `base`, sin ocultas ni carpetas de calidad."""

    base = base.expanduser()
    try:
        base = base.resolve()
    except OSError:
        base = base.absolute()
    if not base.is_dir():
        return []
    targets: list[Path] = []
    try:
        with os.scandir(base) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entry.name.startswith(".") or is_quality_dirname(entry.name):
                    continue
                targets.append(Path(entry.path))
    except OSError as exc:
        logger.warning("No pude listar %s: %s", base, exc)
        return []
    targets.sort(key=lambda path: path.name.casefold())
    return targets


def _norm_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def read_image_size(path: Path) -> tuple[int, int] | None:
    """Lee solo cabeceras (sin cargar píxeles ni aplicar EXIF)."""

    try:
        with Image.open(path) as image:
            size = image.size
        if not size or size[0] <= 0 or size[1] <= 0:
            return None
        return int(size[0]), int(size[1])
    except (UnidentifiedImageError, OSError, ValueError, TypeError):
        return None
    except Exception:
        logger.debug("Tamaño no disponible para %s", path, exc_info=True)
        return None


def _classify_path(path: Path) -> tuple[Path, str | None, str | None]:
    """Devuelve (ruta, tier|None, error|None). Pensado para el pool de hilos."""

    size = read_image_size(path)
    if size is None:
        return path, None, "No pude leer dimensiones."
    return path, quality_tier(*size), None


def iter_folder_images(folder: Path) -> Iterable[Path]:
    """Imágenes bajo `folder`, omitiendo subárboles 4K/HD/Baja."""

    folder = folder.expanduser()
    try:
        root = folder.resolve()
    except OSError:
        root = folder

    def on_error(error: OSError) -> None:
        logger.debug("Sin permiso en %s: %s", getattr(error, "filename", root), error)

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and not is_quality_dirname(name)
        ]
        for name in filenames:
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in IMAGE_EXTENSIONS:
                continue
            yield Path(dirpath, name)


def group_folder_by_quality(
    folder: Path,
    *,
    should_cancel: CancelCheck | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> FolderCascadeResult:
    """Clasifica y mueve las imágenes de una carpeta a 4K/HD/Baja.

    No usa base de datos ni miniaturas. Lee dimensiones en paralelo y mueve
    en serie. Los fallos por archivo se anotan y el resto continúa.
    """

    folder = folder.expanduser()
    try:
        folder = folder.resolve()
    except OSError:
        pass
    result = FolderCascadeResult(folder=folder)
    if not folder.is_dir():
        result.errors.append((str(folder), "La carpeta no existe o no es un directorio."))
        return result

    destinations: dict[str, Path] = {}
    dest_keys: dict[str, str] = {}
    for tier in QUALITY_ORDER:
        path = resolve_subdir(folder, quality_label(tier))
        destinations[tier] = path
        dest_keys[tier] = _norm_key(path)

    paths = list(iter_folder_images(folder))
    total = len(paths)
    result.scanned = total
    if on_progress is not None:
        on_progress(0, total)
    if not paths:
        return result

    classified: list[tuple[Path, str]] = []
    workers = min(_SIZE_WORKERS, max(1, total))
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_classify_path, path): path for path in paths}
            for future in as_completed(futures):
                if should_cancel is not None and should_cancel():
                    for pending in futures:
                        pending.cancel()
                    break
                done += 1
                try:
                    path, tier, error = future.result()
                except Exception as exc:
                    path = futures[future]
                    result.errors.append((str(path), f"Error al leer: {exc}"))
                else:
                    if error or tier is None:
                        result.errors.append((str(path), error or "Sin clasificación."))
                    else:
                        parent_key = _norm_key(path.parent)
                        if parent_key == dest_keys.get(tier):
                            result.skipped += 1
                        else:
                            classified.append((path, tier))
                if on_progress is not None and (
                    done == total or done % _PROGRESS_EVERY == 0 or done == 1
                ):
                    on_progress(done, total)
    except Exception as exc:
        result.errors.append((str(folder), f"No pude clasificar el lote: {exc}"))
        logger.exception("Clasificación en cascada falló en %s", folder)
        return result

    if should_cancel is not None and should_cancel():
        if on_progress is not None and total:
            on_progress(total, total)
        return result

    taken: dict[str, set[str]] = {}
    needed = {tier for _path, tier in classified}
    for tier in needed:
        try:
            destinations[tier] = ensure_directory(destinations[tier])
            dest_keys[tier] = _norm_key(destinations[tier])
            taken[tier] = seed_taken_names(destinations[tier])
        except Exception as exc:
            result.errors.append((str(destinations[tier]), str(exc)))
            destinations.pop(tier, None)

    move_total = len(classified)
    for index, (path, tier) in enumerate(classified, start=1):
        if should_cancel is not None and should_cancel():
            break
        destination = destinations.get(tier)
        if destination is None:
            result.errors.append((str(path), f"Sin carpeta destino para {tier}."))
            continue
        try:
            move_into_uniquified(
                path,
                destination,
                taken.setdefault(tier, set()),
                prepared=True,
                trust_taken=True,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            result.errors.append((str(path), message))
            logger.info("Cascada: no moví %s (%s)", path, message)
            continue
        result.moved[tier] = result.moved.get(tier, 0) + 1
        if on_progress is not None and (
            index == move_total or index % _PROGRESS_EVERY == 0 or index == 1
        ):
            on_progress(index, move_total)

    if on_progress is not None and total:
        on_progress(max(total, move_total), max(total, move_total) or 1)
    return result


def cascade_group_by_quality(
    base: Path,
    *,
    targets: list[Path] | None = None,
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
    on_folder: FolderCallback | None = None,
) -> CascadeResult:
    """Aplica `group_folder_by_quality` a cada subcarpeta de `base`."""

    base = base.expanduser()
    try:
        base = base.resolve()
    except OSError:
        pass
    folders = targets if targets is not None else list_cascade_targets(base)
    outcome = CascadeResult(base=base)
    total = len(folders)
    for index, folder in enumerate(folders, start=1):
        if should_cancel is not None and should_cancel():
            outcome.cancelled = True
            break

        def _folder_progress(current: int, image_total: int, *, _i=index, _f=folder) -> None:
            if on_progress is not None:
                on_progress(_i, total, _f.name, current, image_total)

        try:
            folder_result = group_folder_by_quality(
                folder,
                should_cancel=should_cancel,
                on_progress=_folder_progress if on_progress else None,
            )
        except Exception as exc:
            logger.exception("Cascada falló en %s", folder)
            folder_result = FolderCascadeResult(
                folder=folder,
                errors=[(str(folder), f"Error inesperado: {exc}")],
            )
        outcome.folders.append(folder_result)
        if on_folder is not None:
            try:
                on_folder(folder_result)
            except Exception:
                logger.debug("Callback de carpeta falló", exc_info=True)
        if should_cancel is not None and should_cancel():
            outcome.cancelled = True
            break
    return outcome
