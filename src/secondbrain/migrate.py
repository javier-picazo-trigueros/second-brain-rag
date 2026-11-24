"""Migración de la carpeta de datos locales (manifest, caché de BM25, alias) a otro sitio.

Copia, no mueve: el origen no se toca. Después de copiar se verifica fichero a fichero (tamaño y
huella) y el contenido del manifest (todas sus tablas), y solo entonces se da por buena. Pensada
para sacar `data/` de OneDrive: se fija `BRAIN_DATA_DIR` en el `.env` y se borra el origen a mano
cuando todo funcione.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

MANIFEST = "manifest.sqlite"
_JOURNAL_SUFFIXES = ("-journal", "-wal", "-shm")
_MANIFEST_TABLES = ("notes", "note_concepts", "meta")


class MigrationError(RuntimeError):
    """La migración no se puede hacer o la copia no coincide con el origen."""


@dataclass(frozen=True, slots=True)
class MigrationReport:
    notes: int
    chunks: int
    files: int
    size_bytes: int


def _is_journal(path: Path) -> bool:
    return path.name.startswith(MANIFEST) and path.name.endswith(_JOURNAL_SUFFIXES)


def _files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST and not _is_journal(p)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _manifest_content(path: Path) -> dict[str, list[tuple[object, ...]]]:
    out: dict[str, list[tuple[object, ...]]] = {}
    with closing(_open_readonly(path)) as db:
        for table in _MANIFEST_TABLES:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            out[table] = sorted(db.execute(f"SELECT * FROM {table}").fetchall()) if exists else []
    return out


def verify_copy(source: Path, dest: Path) -> list[str]:
    """Diferencias entre el origen y la copia (lista vacía = idénticos)."""
    problems: list[str] = []
    for path in _files(source):
        relative = path.relative_to(source)
        copy = dest / relative
        if not copy.is_file():
            problems.append(f"falta {relative.as_posix()}")
        elif copy.stat().st_size != path.stat().st_size or _sha256(copy) != _sha256(path):
            problems.append(f"distinto {relative.as_posix()}")
    original, copied = source / MANIFEST, dest / MANIFEST
    if original.exists():
        if not copied.exists():
            problems.append(f"falta el manifest {MANIFEST}")
        else:
            before, after = _manifest_content(original), _manifest_content(copied)
            for table in _MANIFEST_TABLES:
                if before[table] != after[table]:
                    problems.append(
                        f"el manifest no coincide en {table} ({len(before[table])} filas en el "
                        f"origen, {len(after[table])} en la copia)"
                    )
    return problems


def _copy_manifest(source: Path, dest: Path) -> None:
    """Copia consistente aunque otro proceso esté escribiendo (API de copia de SQLite)."""
    with closing(_open_readonly(source)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)


def _totals(manifest: Path) -> tuple[int, int]:
    if not manifest.exists():
        return 0, 0
    with closing(_open_readonly(manifest)) as db:
        notes, chunks = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(n_chunks),0) FROM notes"
        ).fetchone()
    return int(notes), int(chunks)


def migrate_data(source: Path, dest: Path) -> MigrationReport:
    """Copia la carpeta de datos a `dest` y la verifica. No modifica el origen."""
    if not source.is_dir():
        raise MigrationError(f"La carpeta de datos no existe: {source}")
    src, dst = source.resolve(), dest.resolve()
    if dst == src or src in dst.parents or dst in src.parents:
        raise MigrationError(
            "El destino no puede ser el mismo sitio que el origen ni estar dentro de él "
            "(ni al revés)."
        )
    if dst.exists() and any(dst.iterdir()):
        raise MigrationError(f"El destino ya tiene archivos: {dst}. No se sobrescribe nada.")
    dst.mkdir(parents=True, exist_ok=True)
    for path in _files(src):
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if (src / MANIFEST).exists():
        _copy_manifest(src / MANIFEST, dst / MANIFEST)
    problems = verify_copy(src, dst)
    if problems:
        raise MigrationError("La copia no coincide con el origen: " + "; ".join(problems))
    notes, chunks = _totals(dst / MANIFEST)
    files = _files(dst)
    return MigrationReport(notes, chunks, len(files), sum(p.stat().st_size for p in files))
