"""Configuración local leída de variables de entorno y de .env."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@dataclass(frozen=True)
class Settings:
    """Rutas y ajustes que nunca salen de este equipo."""

    data_dir: Path
    db_path: Path
    log_path: Path
    log_level: str
    thumb_size: int

    @property
    def thumb_dir(self) -> Path:
        return self.data_dir / "thumbs"


def project_root() -> Path:
    """Raíz del proyecto en desarrollo, o la carpeta del ejecutable empaquetado."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def asset_path(name: str) -> Path:
    """Resuelve un archivo de pylens/assets, también dentro del ejecutable."""

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS")) / "pylens" / "assets"
    else:
        base = Path(__file__).resolve().parents[1] / "assets"
    return base / name


def read_env_file(path: Path) -> dict[str, str]:
    """Lee un .env sencillo. Las líneas vacías y los comentarios se ignoran."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(file_vars: dict[str, str], key: str, default: str = "") -> str:
    if key in os.environ:
        return os.environ[key]
    return file_vars.get(key, default)


def load_settings() -> Settings:
    """Construye la configuración. Una variable ya exportada pisa al archivo .env."""

    file_vars = read_env_file(project_root() / ".env")
    raw_dir = _setting(file_vars, "PYLENS_DATA_DIR").strip()
    data_dir = Path(raw_dir).expanduser() if raw_dir else Path.home() / ".pylens"
    level = _setting(file_vars, "PYLENS_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    if level not in _LOG_LEVELS:
        level = "INFO"
    raw_thumb = _setting(file_vars, "PYLENS_THUMB_SIZE", "320").strip() or "320"
    try:
        thumb_size = int(raw_thumb)
    except ValueError:
        thumb_size = 320
    thumb_size = min(max(thumb_size, 96), 800)
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "pylens.sqlite3",
        log_path=data_dir / "pylens.log",
        log_level=level,
        thumb_size=thumb_size,
    )
