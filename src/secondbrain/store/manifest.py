from __future__ import annotations

import sqlite3
import threading
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

    def close(self) -> None:
        with self._lock:
            self._db.close()
