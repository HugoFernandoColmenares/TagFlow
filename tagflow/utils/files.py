"""Operaciones de archivo: renombrar, mover, agrupar, comprimir y optimizar."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from tagflow.core.errors import UserError

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"}
_RESERVED.update({f"COM{index}" for index in range(1, 10)})
_RESERVED.update({f"LPT{index}" for index in range(1, 10)})


def sanitize_filename(name: str) -> str:
    """Limpia un nombre para que Windows pueda crearlo."""

    cleaned = _INVALID.sub("", name).strip().strip(".")
    cleaned = cleaned.rstrip(" .")
    if not cleaned or cleaned in {".", ".."}:
        raise UserError("El nombre no es válido en Windows.")
    stem = cleaned.split(".", 1)[0].upper()
    if stem in _RESERVED:
        raise UserError("Ese nombre está reservado por Windows.")
    return cleaned


def rename_file(src: Path, new_name: str) -> Path:
    """Renombra en la misma carpeta. Si no hay extensión, conserva la actual."""

    cleaned = sanitize_filename(new_name)
    if Path(cleaned).suffix == "" and src.suffix:
        cleaned = f"{cleaned}{src.suffix}"
    target = src.with_name(cleaned)
    if target == src:
        return src
    if target.exists():
        raise UserError("Ya existe un archivo con ese nombre.")
    try:
        src.rename(target)
    except OSError as exc:
        raise UserError(f"No pude renombrar {src.name}: {exc.strerror or exc}") from exc
    return target


def move_file(src: Path, dest_dir: Path) -> Path:
    """Mueve un archivo a otra carpeta, también entre unidades."""

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    if target.resolve() == src.resolve():
        return src
    if target.exists():
        raise UserError(f"Ya existe un archivo llamado {target.name} en esa carpeta.")
    try:
        shutil.move(str(src), str(target))
    except OSError as exc:
        raise UserError(f"No pude mover {src.name}: {exc.strerror or exc}") from exc
    return Path(target)


def delete_file(path: Path) -> None:
    """Elimina el archivo del disco. Si ya no está, no hace nada."""

    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise UserError(f"No pude eliminar {path.name}: {exc.strerror or exc}") from exc


def group_files(paths: list[Path], destination: Path) -> list[tuple[Path, Path]]:
    """Crea la carpeta destino y mueve el lote. Si algo falla, deshace lo movido."""

    if not paths:
        raise UserError("Selecciona imágenes para agrupar.")
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UserError(f"No pude crear la carpeta: {exc.strerror or exc}") from exc
    planned: list[tuple[Path, Path]] = []
    for src in paths:
        if destination.resolve() == src.parent.resolve():
            continue
        target = destination / src.name
        if target.exists():
            raise UserError(f"Ya existe {target.name} dentro de la carpeta de destino.")
        planned.append((src, target))
    if not planned:
        return []
    moved: list[tuple[Path, Path]] = []
    try:
        for src, target in planned:
            shutil.move(str(src), str(target))
            moved.append((src, Path(target)))
    except OSError as exc:
        for src, target in reversed(moved):
            if target.exists() and not src.exists():
                shutil.move(str(target), str(src))
        raise UserError(f"No pude mover los archivos: {exc.strerror or exc}") from exc
    return moved


def zip_files(paths: list[Path], archive: Path, base: Path | None = None) -> Path:
    """Empaqueta las imágenes. Con `base`, conserva la ruta relativa a esa carpeta."""

    unique: list[Path] = []
    seen: set[str] = set()
    archive_resolved = archive.resolve()
    for path in paths:
        key = str(path.resolve()).casefold()
        if key in seen or path.resolve() == archive_resolved:
            continue
        seen.add(key)
        if not path.is_file():
            raise UserError(f"No encuentro {path.name}.")
        unique.append(path)
    if not unique:
        raise UserError("No hay archivos para comprimir.")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if base is None:
        try:
            base = Path(os.path.commonpath([str(path.parent) for path in unique]))
        except ValueError:
            base = None
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            used: set[str] = set()
            for path in unique:
                arcname = path.name
                if base is not None:
                    try:
                        arcname = path.resolve().relative_to(base.resolve()).as_posix()
                    except ValueError:
                        arcname = path.name
                if arcname.casefold() in used:
                    arcname = f"{path.parent.name}/{path.name}"
                used.add(arcname.casefold())
                bundle.write(path, arcname=arcname)
    except OSError as exc:
        raise UserError(f"No pude crear el archivo zip: {exc.strerror or exc}") from exc
    return archive


def optimize_image(path: Path, quality: int = 85) -> tuple[int, int]:
    """Recomprime JPEG, WebP o PNG en el mismo sitio y devuelve el peso anterior y el nuevo."""

    if not 40 <= quality <= 95:
        raise UserError("La calidad debe estar entre 40 y 95.")
    extension = path.suffix.lower()
    if extension not in {".jpg", ".jpeg", ".webp", ".png"}:
        raise UserError(f"{path.name} no se puede optimizar desde TagFlow.")
    old_size = path.stat().st_size
    temporary = path.with_name(f".{path.stem}.tagflow-opt{path.suffix}")
    try:
        with Image.open(path) as image:
            image.load()
            if extension in {".jpg", ".jpeg"}:
                image.convert("RGB").save(temporary, "JPEG", quality=quality, optimize=True)
            elif extension == ".webp":
                image.convert("RGB").save(temporary, "WEBP", quality=quality, method=6)
            else:
                image.save(temporary, "PNG", optimize=True)
        temporary.replace(path)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise UserError(f"No pude optimizar {path.name}: {exc}") from exc
    return old_size, path.stat().st_size
