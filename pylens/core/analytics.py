"""Estadísticas calculadas sobre el índice, sin volver a recorrer el disco."""

from __future__ import annotations

from pathlib import Path

from pylens.core.models import ImageRecord, LibraryStats
from pylens.utils.text import QUALITY_ORDER


def folder_depth(scan_root: str, folder: str) -> int:
    """Niveles de subcarpeta respecto a la raíz indexada."""

    try:
        relative = Path(folder).resolve().relative_to(Path(scan_root).resolve())
    except ValueError:
        return 0
    if str(relative) == ".":
        return 0
    return len(relative.parts)


def summarize(records: list[ImageRecord]) -> LibraryStats:
    """Resume la vista filtrada: peso, formatos, calidad, etiquetas y profundidad."""

    qualities = {tier: 0 for tier in QUALITY_ORDER}
    if not records:
        return LibraryStats(qualities=qualities)
    formats: dict[str, int] = {}
    tags: dict[str, tuple[str, int]] = {}
    total_bytes = 0
    total_bpp = 0.0
    max_depth = 0
    for record in records:
        total_bytes += record.size_bytes
        total_bpp += record.bytes_per_pixel
        formats[record.format] = formats.get(record.format, 0) + 1
        if record.quality_tier in qualities:
            qualities[record.quality_tier] += 1
        else:
            qualities[record.quality_tier] = qualities.get(record.quality_tier, 0) + 1
        max_depth = max(max_depth, folder_depth(record.scan_root, record.folder))
        for tag in record.tags:
            key = tag.casefold()
            label, count = tags.get(key, (tag, 0))
            tags[key] = (label, count + 1)
    count = len(records)
    format_rows = sorted(formats.items(), key=lambda item: (-item[1], item[0].casefold()))
    tag_rows = sorted(tags.values(), key=lambda item: (-item[1], item[0].casefold()))
    return LibraryStats(
        count=count,
        total_bytes=total_bytes,
        average_bytes=total_bytes / count,
        average_bpp=total_bpp / count,
        max_depth=max_depth,
        formats=format_rows,
        qualities=qualities,
        tags=tag_rows,
        dominant_format=format_rows[0][0] if format_rows else None,
    )
