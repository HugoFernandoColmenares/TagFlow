"""Exportaciones del núcleo."""

from tagflow.core.analytics import summarize
from tagflow.core.database import Database
from tagflow.core.duplicates import group_by_exact, group_by_name, group_by_phash
from tagflow.core.scanner import discover_images, extract_metadata

__all__ = [
    "Database",
    "discover_images",
    "extract_metadata",
    "group_by_exact",
    "group_by_name",
    "group_by_phash",
    "summarize",
]
