"""Índice SQLite: metadatos, etiquetas, hashes y el registro de errores."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pylens.core.errors import UserError
from pylens.core.models import ErrorEntry, ImageRecord

_COLUMNS = (
    "id",
    "path",
    "filename",
    "folder",
    "extension",
    "width",
    "height",
    "size_bytes",
    "format",
    "quality_tier",
    "bytes_per_pixel",
    "sharpness",
    "md5",
    "sha256",
    "phash",
    "tags",
    "mtime_ns",
    "scan_root",
    "thumb_path",
    "indexed_at",
)
_SELECT = ", ".join(_COLUMNS)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    folder TEXT NOT NULL,
    extension TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    format TEXT NOT NULL,
    quality_tier TEXT NOT NULL,
    bytes_per_pixel REAL NOT NULL,
    sharpness REAL,
    md5 TEXT,
    sha256 TEXT,
    phash TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    mtime_ns INTEGER NOT NULL,
    scan_root TEXT NOT NULL,
    thumb_path TEXT,
    indexed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_images_scan_root ON images(scan_root);
CREATE INDEX IF NOT EXISTS idx_images_md5 ON images(md5);

CREATE TABLE IF NOT EXISTS error_ledger (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    level TEXT NOT NULL,
    path TEXT,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def normalize_tags(tags: list[str]) -> list[str]:
    """Limpia etiquetas, descarta vacíos y unifica duplicados sin distinguir mayúsculas."""

    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = " ".join(tag.strip().split())
        if not cleaned:
            continue
        if len(cleaned) > 40:
            raise UserError("Cada etiqueta puede tener hasta 40 caracteres.")
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


class Database:
    """Conexión usada solo desde el hilo de la interfaz."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")

    def initialize(self) -> None:
        """Crea el esquema versión 1 si la base está vacía."""

        self.conn.executescript(_SCHEMA)
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def log_error(self, message: str, path: str | None = None, level: str = "ERROR") -> None:
        self.conn.execute(
            "INSERT INTO error_ledger (created_at, level, path, message) VALUES (?, ?, ?, ?)",
            (_now(), level, path, message),
        )
        self.conn.commit()

    def list_errors(self, limit: int = 200) -> list[ErrorEntry]:
        rows = self.conn.execute(
            """
            SELECT id, created_at, level, path, message
            FROM error_ledger
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            ErrorEntry(
                id=int(row["id"]),
                created_at=str(row["created_at"]),
                level=str(row["level"]),
                path=None if row["path"] is None else str(row["path"]),
                message=str(row["message"]),
            )
            for row in rows
        ]

    def count_errors(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS total FROM error_ledger").fetchone()
        return int(row["total"])

    def upsert_image(self, record: ImageRecord) -> ImageRecord:
        """Inserta o actualiza por ruta. Conserva etiquetas y los hashes si el archivo no cambió."""

        tags = json.dumps(normalize_tags(record.tags), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO images (
                path, filename, folder, extension, width, height, size_bytes, format,
                quality_tier, bytes_per_pixel, sharpness, md5, sha256, phash, tags,
                mtime_ns, scan_root, thumb_path, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                filename = excluded.filename,
                folder = excluded.folder,
                extension = excluded.extension,
                width = excluded.width,
                height = excluded.height,
                size_bytes = excluded.size_bytes,
                format = excluded.format,
                quality_tier = excluded.quality_tier,
                bytes_per_pixel = excluded.bytes_per_pixel,
                sharpness = excluded.sharpness,
                md5 = CASE
                    WHEN images.mtime_ns = excluded.mtime_ns AND images.size_bytes = excluded.size_bytes
                    THEN images.md5 ELSE NULL END,
                sha256 = CASE
                    WHEN images.mtime_ns = excluded.mtime_ns AND images.size_bytes = excluded.size_bytes
                    THEN images.sha256 ELSE NULL END,
                phash = CASE
                    WHEN images.mtime_ns = excluded.mtime_ns AND images.size_bytes = excluded.size_bytes
                    THEN images.phash ELSE NULL END,
                tags = images.tags,
                mtime_ns = excluded.mtime_ns,
                scan_root = excluded.scan_root,
                thumb_path = excluded.thumb_path,
                indexed_at = excluded.indexed_at
            """,
            (
                record.path,
                record.filename,
                record.folder,
                record.extension,
                record.width,
                record.height,
                record.size_bytes,
                record.format,
                record.quality_tier,
                record.bytes_per_pixel,
                record.sharpness,
                record.md5,
                record.sha256,
                record.phash,
                tags,
                record.mtime_ns,
                record.scan_root,
                record.thumb_path,
                _now(),
            ),
        )
        self.conn.commit()
        stored = self.get_by_path(record.path)
        if stored is None:
            raise UserError(f"No pude guardar el índice de {record.filename}.")
        return stored

    def get_by_path(self, path: str) -> ImageRecord | None:
        row = self.conn.execute(f"SELECT {_SELECT} FROM images WHERE path = ?", (path,)).fetchone()
        return None if row is None else _record(row)

    def get_by_id(self, image_id: int) -> ImageRecord | None:
        row = self.conn.execute(f"SELECT {_SELECT} FROM images WHERE id = ?", (image_id,)).fetchone()
        return None if row is None else _record(row)

    def query_images(
        self,
        scan_root: str,
        *,
        quality: str | None = None,
        weight: str | None = None,
        tags: list[str] | None = None,
        text: str = "",
    ) -> list[ImageRecord]:
        clauses = ["scan_root = ?"]
        params: list[object] = [scan_root]
        if quality and quality != "any":
            clauses.append("quality_tier = ?")
            params.append(quality)
        if weight == "lt500":
            clauses.append("size_bytes < ?")
            params.append(500 * 1024)
        elif weight == "mid":
            clauses.append("size_bytes >= ? AND size_bytes <= ?")
            params.extend([500 * 1024, 5 * 1024 * 1024])
        elif weight == "gt5":
            clauses.append("size_bytes > ?")
            params.append(5 * 1024 * 1024)
        needle = text.strip()
        if needle:
            clauses.append("filename LIKE ? ESCAPE '\\'")
            params.append(_like_contains(needle))
        for tag in tags or []:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(images.tags) WHERE lower(value) = lower(?))"
            )
            params.append(tag)
        sql = (
            f"SELECT {_SELECT} FROM images WHERE {' AND '.join(clauses)} "
            "ORDER BY filename COLLATE NOCASE"
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [_record(row) for row in rows]

    def list_root(self, scan_root: str) -> list[ImageRecord]:
        return self.query_images(scan_root)

    def distinct_tags(self, scan_root: str) -> list[str]:
        rows = self.conn.execute("SELECT tags FROM images WHERE scan_root = ?", (scan_root,)).fetchall()
        found: dict[str, str] = {}
        for row in rows:
            for tag in json.loads(row["tags"] or "[]"):
                found.setdefault(str(tag).casefold(), str(tag))
        return [found[key] for key in sorted(found)]

    def update_tags(self, image_id: int, tags: list[str]) -> None:
        payload = json.dumps(normalize_tags(tags), ensure_ascii=False)
        self.conn.execute("UPDATE images SET tags = ? WHERE id = ?", (payload, image_id))
        self.conn.commit()

    def update_hashes(
        self,
        image_id: int,
        *,
        md5: str | None = None,
        sha256: str | None = None,
        phash: str | None = None,
        exact: bool = False,
        perceptual: bool = False,
    ) -> None:
        sets: list[str] = []
        params: list[object] = []
        if exact:
            sets.extend(["md5 = ?", "sha256 = ?"])
            params.extend([md5, sha256])
        if perceptual:
            sets.append("phash = ?")
            params.append(phash)
        if not sets:
            return
        params.append(image_id)
        self.conn.execute(f"UPDATE images SET {', '.join(sets)} WHERE id = ?", params)
        self.conn.commit()

    def update_technical(self, image_id: int, record: ImageRecord) -> None:
        """Actualiza medidas tras optimizar. El contenido cambió, así que borra hashes."""

        self.conn.execute(
            """
            UPDATE images SET
                filename = ?, folder = ?, extension = ?, width = ?, height = ?,
                size_bytes = ?, format = ?, quality_tier = ?, bytes_per_pixel = ?,
                sharpness = ?, mtime_ns = ?, thumb_path = ?,
                md5 = NULL, sha256 = NULL, phash = NULL, indexed_at = ?
            WHERE id = ?
            """,
            (
                record.filename,
                record.folder,
                record.extension,
                record.width,
                record.height,
                record.size_bytes,
                record.format,
                record.quality_tier,
                record.bytes_per_pixel,
                record.sharpness,
                record.mtime_ns,
                record.thumb_path,
                _now(),
                image_id,
            ),
        )
        self.conn.commit()

    def relocate(self, image_id: int, new_path: Path, thumb_path: str | None, mtime_ns: int) -> None:
        """Actualiza la ruta tras mover o renombrar. Los hashes siguen siendo válidos."""

        self.conn.execute(
            """
            UPDATE images SET
                path = ?, filename = ?, folder = ?, extension = ?,
                thumb_path = ?, mtime_ns = ?
            WHERE id = ?
            """,
            (
                str(new_path),
                new_path.name,
                str(new_path.parent),
                new_path.suffix.lower(),
                thumb_path,
                mtime_ns,
                image_id,
            ),
        )
        self.conn.commit()

    def delete_image(self, image_id: int) -> None:
        self.conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        self.conn.commit()

    def prune(self, scan_root: str, seen: set[str]) -> int:
        """Quita del índice las rutas de esta raíz que ya no aparecieron en el análisis."""

        rows = self.conn.execute("SELECT id, path FROM images WHERE scan_root = ?", (scan_root,)).fetchall()
        stale = [int(row["id"]) for row in rows if str(row["path"]) not in seen]
        for image_id in stale:
            self.conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        if stale:
            self.conn.commit()
        return len(stale)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _like_contains(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _record(row: sqlite3.Row) -> ImageRecord:
    try:
        tags = [str(tag) for tag in json.loads(row["tags"] or "[]")]
    except json.JSONDecodeError:
        tags = []
    return ImageRecord(
        id=int(row["id"]),
        path=str(row["path"]),
        filename=str(row["filename"]),
        folder=str(row["folder"]),
        extension=str(row["extension"]),
        width=int(row["width"]),
        height=int(row["height"]),
        size_bytes=int(row["size_bytes"]),
        format=str(row["format"]),
        quality_tier=str(row["quality_tier"]),
        bytes_per_pixel=float(row["bytes_per_pixel"]),
        sharpness=None if row["sharpness"] is None else float(row["sharpness"]),
        md5=None if row["md5"] is None else str(row["md5"]),
        sha256=None if row["sha256"] is None else str(row["sha256"]),
        phash=None if row["phash"] is None else str(row["phash"]),
        tags=tags,
        mtime_ns=int(row["mtime_ns"]),
        scan_root=str(row["scan_root"]),
        thumb_path=None if row["thumb_path"] is None else str(row["thumb_path"]),
    )
