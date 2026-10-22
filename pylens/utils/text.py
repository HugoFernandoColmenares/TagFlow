"""Presentación de tamaños y niveles de calidad."""

from __future__ import annotations

QUALITY_ORDER = ("4K", "HD", "Low-res")
QUALITY_LABELS = {"4K": "4K", "HD": "HD", "Low-res": "Baja"}


def format_bytes(size: int) -> str:
    """Convierte bytes a una magnitud legible."""

    value = float(max(size, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def quality_label(tier: str) -> str:
    return QUALITY_LABELS.get(tier, tier)
