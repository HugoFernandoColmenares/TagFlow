"""Configuración local."""

from __future__ import annotations

from pathlib import Path

from pylens.utils.config import load_settings, read_env_file


def test_env_file_ignores_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comentario\n\nPYLENS_LOG_LEVEL = DEBUG\n", encoding="utf-8")
    assert read_env_file(env) == {"PYLENS_LOG_LEVEL": "DEBUG"}


def test_environment_overrides_dotenv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYLENS_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("PYLENS_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("PYLENS_THUMB_SIZE", "180")
    settings = load_settings()
    assert settings.data_dir == tmp_path / "datos"
    assert settings.db_path == tmp_path / "datos" / "pylens.sqlite3"
    assert settings.log_level == "ERROR"
    assert settings.thumb_size == 180


def test_invalid_values_fall_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYLENS_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("PYLENS_LOG_LEVEL", "NO-EXISTE")
    monkeypatch.setenv("PYLENS_THUMB_SIZE", "mucho")
    settings = load_settings()
    assert settings.log_level == "INFO"
    assert settings.thumb_size == 320
