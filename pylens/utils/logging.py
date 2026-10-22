"""Registro en archivo local, complementario al libro de errores de SQLite."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_path: Path, level: str) -> None:
    """Configura el registro una sola vez por proceso."""

    root = logging.getLogger()
    if getattr(root, "_pylens_ready", False):
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    root._pylens_ready = True  # type: ignore[attr-defined]
