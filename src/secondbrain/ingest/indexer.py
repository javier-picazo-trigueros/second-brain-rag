from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from secondbrain.config import Settings
from secondbrain.ingest.chunker import chunk_note
from secondbrain.ingest.parser import parse_note
from secondbrain.protocols import Embedder, Store
from secondbrain.store.manifest import Manifest

log = logging.getLogger(__name__)
Status = Literal["indexed", "unchanged", "empty"]


@dataclass(slots=True)
class SyncReport:
    indexed: int = 0
    unchanged: int = 0
    empty: int = 0
    deleted: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


class Indexer:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        store: Store,
        manifest: Manifest,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._now = now
        self._s = settings
        self._embedder = embedder
        self._store = store
        self._manifest = manifest
        self._fingerprint = settings.index_fingerprint

    def _rel(self, abs_path: Path) -> str:
        return abs_path.relative_to(self._s.vault_path).as_posix()

    def iter_note_paths(self) -> Iterator[Path]:
        for root, dirs, files in os.walk(self._s.vault_path):
            # Poda en sitio: no se entra en node_modules, .obsidian, _conceptos...
            dirs[:] = sorted(d for d in dirs if d not in self._s.exclude_dirs)
            for f in sorted(files):
                path = Path(root) / f
                if f.lower().endswith(".md") and not self._s.is_excluded(self._rel(path)):
                    yield path

    def index_file(self, abs_path: Path) -> Status:
        note = parse_note(abs_path, self._s.vault_path)
        # El hash incluye la huella de configuración: cambiar modelo o chunking reindexa todo.
        stamp = f"{note.content_hash}:{self._fingerprint}"
        if self._manifest.get(note.path) == stamp:
            # Conceptos y copias se refrescan siempre: es barato y evita reindexar al añadirlos.
            self._manifest.set_meta(note.path, note.concepts, note.body_hash)
            return "unchanged"
        chunks = (
            []
            if note.frontmatter.get("sin_texto") is True
            else chunk_note(note, self._s.chunk_max_chars, self._s.chunk_min_chars)
        )
        # Se embebe antes de borrar: si falla, los chunks anteriores siguen intactos.
        vectors = self._embedder.embed_documents([c.embed_text for c in chunks]) if chunks else []
        self._store.delete_note(note.path)
        if chunks:
            self._store.upsert_chunks(chunks, vectors)
        self._manifest.upsert(note.path, stamp, len(chunks))
        self._manifest.set_meta(note.path, note.concepts, note.body_hash)
        return "indexed" if chunks else "empty"

    def is_indexed(self, rel_path: str) -> bool:
        return self._manifest.get(rel_path) is not None

    def remove(self, rel_path: str) -> None:
        self._store.delete_note(rel_path)
        self._manifest.delete(rel_path)

    def sync(self, on_progress: Callable[[int, int, str], None] | None = None) -> SyncReport:
        report = SyncReport()
        seen: set[str] = set()
        paths = list(self.iter_note_paths())
        for position, abs_path in enumerate(paths, start=1):
            rel = abs_path.relative_to(self._s.vault_path).as_posix()
            seen.add(rel)
            try:
                status = self.index_file(abs_path)
            except Exception as exc:  # una nota rota no debe parar el sync; se registra y reporta
                log.exception("Fallo indexando %s", rel)
                report.failed.append((rel, repr(exc)))
            else:
                if status == "indexed":
                    report.indexed += 1
                    log.info("indexada: %s", rel)
                elif status == "empty":
                    report.empty += 1
                else:
                    report.unchanged += 1
            if on_progress is not None:
                on_progress(position, len(paths), rel)
        for gone in self._manifest.paths() - seen:
            self.remove(gone)
            report.deleted += 1
        self._manifest.set_value("last_sync", self._now().isoformat())
        return report
