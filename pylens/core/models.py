"""Modelos de datos que comparten el índice, el análisis y la interfaz."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageRecord:
    """Metadatos de una imagen indexada."""

    path: str
    filename: str
    folder: str
    extension: str
    width: int
    height: int
    size_bytes: int
    format: str
    quality_tier: str
    bytes_per_pixel: float
    sharpness: float | None
    md5: str | None
    sha256: str | None
    phash: str | None
    tags: list[str]
    mtime_ns: int
    scan_root: str
    thumb_path: str | None = None
    id: int | None = None


@dataclass
class ErrorEntry:
    """Línea del registro local de errores."""

    id: int
    created_at: str
    level: str
    path: str | None
    message: str


@dataclass
class LibraryStats:
    """Métricas de la vista actual, no de un segundo recorrido del disco."""

    count: int = 0
    total_bytes: int = 0
    average_bytes: float = 0.0
    average_bpp: float = 0.0
    max_depth: int = 0
    formats: list[tuple[str, int]] = field(default_factory=list)
    qualities: dict[str, int] = field(default_factory=dict)
    tags: list[tuple[str, int]] = field(default_factory=list)
    dominant_format: str | None = None


@dataclass(frozen=True)
class DuplicateGroup:
    """Conjunto de imágenes que comparten nombre, bytes o aspecto."""

    kind: str
    title: str
    detail: str
    image_ids: tuple[int, ...]
