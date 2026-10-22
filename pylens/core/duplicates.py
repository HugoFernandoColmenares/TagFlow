"""Detección de duplicados por nombre, hash criptográfico y pHash."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pylens.core.errors import UserError
from pylens.core.imaging import compute_phash
from pylens.core.models import DuplicateGroup, ImageRecord

_SUFFIX = re.compile(
    r"(?i)(?:\s*\(\d+\)|\s*-\s*(?:copy|copia)|\s*\((?:copy|copia)\)|\s+(?:copy|copia)|_(?:copy|copia))$"
)
_PHASH_DISTANCE = 8


def canonical_stem(stem: str) -> str:
    """Quita sufijos de copia de Windows, en español e inglés, repetidos."""

    current = stem.strip()
    for _ in range(6):
        updated = _SUFFIX.sub("", current).strip()
        if updated == current:
            break
        current = updated
    return current.casefold()


def normalize_ext(extension: str) -> str:
    ext = extension.lower()
    if ext == ".jpeg":
        return ".jpg"
    return ext


def hamming(left: str, right: str) -> int:
    """Distancia de Hamming entre dos pHash hexadecimales."""

    if len(left) != len(right):
        return 64
    return (int(left, 16) ^ int(right, 16)).bit_count()


def hash_file(path: Path) -> tuple[str, str]:
    """Calcula MD5 y SHA-256 en una sola lectura."""

    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                md5.update(chunk)
                sha256.update(chunk)
    except OSError as exc:
        raise UserError(f"No pude leer {path.name}: {exc.strerror or exc}") from exc
    return md5.hexdigest(), sha256.hexdigest()


def perceptual_hash(path: Path) -> str | None:
    return compute_phash(path)


def group_by_name(records: list[ImageRecord]) -> list[DuplicateGroup]:
    """Agrupa `foto.jpg` con `foto (1).jpg`, `foto - copia.jpg` y variantes."""

    buckets: dict[tuple[str, str, str], list[ImageRecord]] = {}
    for record in records:
        if record.id is None:
            continue
        stem = canonical_stem(Path(record.filename).stem)
        if not stem:
            continue
        key = (record.folder.casefold(), stem, normalize_ext(record.extension))
        buckets.setdefault(key, []).append(record)
    groups: list[DuplicateGroup] = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda item: (len(item.filename), item.filename.casefold()))
        groups.append(
            DuplicateGroup(
                kind="name",
                title=ordered[0].filename,
                detail="Mismo nombre base en la misma carpeta",
                image_ids=tuple(item.id for item in ordered if item.id is not None),
            )
        )
    return _sorted(groups)


def group_by_exact(records: list[ImageRecord]) -> list[DuplicateGroup]:
    """Agrupa archivos con el mismo MD5. El SHA-256 se informa si también coincide."""

    buckets: dict[str, list[ImageRecord]] = {}
    for record in records:
        if record.id is None or not record.md5:
            continue
        buckets.setdefault(record.md5, []).append(record)
    groups: list[DuplicateGroup] = []
    for digest, items in buckets.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda item: item.path.casefold())
        sha_values = {item.sha256 for item in ordered if item.sha256}
        if len(sha_values) == 1:
            detail = "Mismos bytes (MD5 y SHA-256)"
        else:
            detail = "MD5 idéntico"
        groups.append(
            DuplicateGroup(
                kind="md5",
                title=digest[:12],
                detail=detail,
                image_ids=tuple(item.id for item in ordered if item.id is not None),
            )
        )
    return _sorted(groups)


def group_by_phash(
    records: list[ImageRecord],
    max_distance: int = _PHASH_DISTANCE,
) -> list[DuplicateGroup]:
    """Agrupa imágenes visualmente cercanas aunque el nombre o el formato cambien."""

    hashed = [record for record in records if record.id is not None and record.phash]
    parent = {record.id: record.id for record in hashed if record.id is not None}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for index, left in enumerate(hashed):
        assert left.id is not None and left.phash is not None
        for right in hashed[index + 1 :]:
            assert right.id is not None and right.phash is not None
            if hamming(left.phash, right.phash) <= max_distance:
                union(left.id, right.id)
    clusters: dict[int, list[ImageRecord]] = {}
    for record in hashed:
        assert record.id is not None
        clusters.setdefault(find(record.id), []).append(record)
    groups: list[DuplicateGroup] = []
    for items in clusters.values():
        if len(items) < 2:
            continue
        distances: list[int] = []
        for index, left in enumerate(items):
            assert left.phash is not None
            for right in items[index + 1 :]:
                assert right.phash is not None
                distances.append(hamming(left.phash, right.phash))
        farthest = max(distances) if distances else 0
        ordered = sorted(items, key=lambda item: item.filename.casefold())
        representative = max(ordered, key=lambda item: (item.size_bytes, -len(item.filename)))
        groups.append(
            DuplicateGroup(
                kind="phash",
                title=representative.filename,
                detail=f"Aspecto similar (pHash, distancia máxima {farthest})",
                image_ids=tuple(item.id for item in ordered if item.id is not None),
            )
        )
    return _sorted(groups)


def _sorted(groups: list[DuplicateGroup]) -> list[DuplicateGroup]:
    return sorted(groups, key=lambda group: (-len(group.image_ids), group.title.casefold()))
