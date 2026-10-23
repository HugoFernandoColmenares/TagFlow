"""Configuración local."""

from __future__ import annotations

from pathlib import Path

from tagflow.utils.config import load_settings, read_env_file


def test_env_file_ignores_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comentario\n\nTAGFLOW_LOG_LEVEL = DEBUG\n", encoding="utf-8")
    assert read_env_file(env) == {"TAGFLOW_LOG_LEVEL": "DEBUG"}


def test_environment_overrides_dotenv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAGFLOW_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("TAGFLOW_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("TAGFLOW_THUMB_SIZE", "180")
    settings = load_settings()
    assert settings.data_dir == tmp_path / "datos"
    assert settings.db_path == tmp_path / "datos" / "tagflow.sqlite3"
    assert settings.log_level == "ERROR"
    assert settings.thumb_size == 180


def test_invalid_values_fall_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAGFLOW_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("TAGFLOW_LOG_LEVEL", "NO-EXISTE")
    monkeypatch.setenv("TAGFLOW_THUMB_SIZE", "mucho")
    settings = load_settings()
    assert settings.log_level == "INFO"
    assert settings.thumb_size == 320
