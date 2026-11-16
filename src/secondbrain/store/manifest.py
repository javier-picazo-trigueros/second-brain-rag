from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path


class Manifest:
    """Ruta -> hash del contenido indexado. Permite sincronizar de forma incremental."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS notes ("
                "path TEXT PRIMARY KEY, hash TEXT NOT NULL, n_chunks INTEGER NOT NULL)"
            )
            # Migración: las bases creadas en la fase 1 no tienen body_hash.
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(notes)")}
            if "body_hash" not in columns:
                self._db.execute("ALTER TABLE notes ADD COLUMN body_hash TEXT")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS note_concepts ("
                "path TEXT NOT NULL, concept TEXT NOT NULL, pos INTEGER NOT NULL, "
                "PRIMARY KEY (path, concept))"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_concepts_concept ON note_concepts(concept)"
            )
            self._db.commit()

    def get(self, path: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT hash FROM notes WHERE path=?", (path,)).fetchone()
        return None if row is None else str(row[0])

    def upsert(self, path: str, content_hash: str, n_chunks: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO notes(path, hash, n_chunks) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, n_chunks=excluded.n_chunks",
                (path, content_hash, n_chunks),
            )
            self._db.commit()

    def delete(self, path: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM notes WHERE path=?", (path,))
            self._db.execute("DELETE FROM note_concepts WHERE path=?", (path,))
            self._db.commit()

    def paths(self) -> set[str]:
        with self._lock:
            return {str(r[0]) for r in self._db.execute("SELECT path FROM notes")}

    def totals(self) -> tuple[int, int]:
        with self._lock:
            n, c = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(n_chunks),0) FROM notes"
            ).fetchone()
        return int(n), int(c)

    def set_meta(self, path: str, concepts: Sequence[str], body_hash: str | None) -> None:
        """Guarda los conceptos y la huella del cuerpo de una nota ya registrada."""
        with self._lock:
            cur = self._db.execute("UPDATE notes SET body_hash=? WHERE path=?", (body_hash, path))
            if cur.rowcount == 0:
                raise KeyError(f"La nota no está en el manifest: {path}")
            self._db.execute("DELETE FROM note_concepts WHERE path=?", (path,))
            self._db.executemany(
                "INSERT OR IGNORE INTO note_concepts(path, concept, pos) VALUES(?,?,?)",
                [(path, c, i) for i, c in enumerate(concepts)],
            )
            self._db.commit()

    def note_concepts(self) -> dict[str, tuple[str, ...]]:
        """Nota -> conceptos, incluidas las notas sin conceptos."""
        with self._lock:
            result: dict[str, list[str]] = {
                str(r[0]): [] for r in self._db.execute("SELECT path FROM notes")
            }
            rows = self._db.execute("SELECT path, concept FROM note_concepts ORDER BY path, pos")
            for path, concept in rows:
                result[str(path)].append(str(concept))
        return {path: tuple(cs) for path, cs in result.items()}

    def duplicate_groups(self) -> list[tuple[str, ...]]:
        """Grupos de notas con el mismo cuerpo normalizado (copias exactas), ordenados."""
        with self._lock:
            rows = self._db.execute(
                "SELECT body_hash, path FROM notes WHERE body_hash IS NOT NULL ORDER BY path"
            )
            groups: dict[str, list[str]] = defaultdict(list)
            for body_hash, path in rows:
                groups[str(body_hash)].append(str(path))
        return sorted(tuple(v) for v in groups.values() if len(v) > 1)

    def chunk_counts(self) -> dict[str, int]:
        with self._lock:
            return {str(p): int(n) for p, n in self._db.execute("SELECT path, n_chunks FROM notes")}

    def close(self) -> None:
        with self._lock:
            self._db.close()
