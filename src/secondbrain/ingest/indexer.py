from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
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
        self, settings: Settings, embedder: Embedder, store: Store, manifest: Manifest
    ) -> None:
        self._s = settings
        self._embedder = embedder
        self._store = store
        self._manifest = manifest
        self._fingerprint = settings.index_fingerprint

    def iter_note_paths(self) -> Iterator[Path]:
        for root, dirs, files in os.walk(self._s.vault_path):
            # Poda en sitio: no se entra en node_modules, .obsidian, _conceptos...
            dirs[:] = sorted(d for d in dirs if d not in self._s.exclude_dirs)
            for f in sorted(files):
                if f.lower().endswith(".md") and f not in self._s.exclude_files:
                    yield Path(root) / f

    def index_file(self, abs_path: Path) -> Status:
        note = parse_note(abs_path, self._s.vault_path)
        # El hash incluye la huella de configuración: cambiar modelo o chunking reindexa todo.
        stamp = f"{note.content_hash}:{self._fingerprint}"
        if self._manifest.get(note.path) == stamp:
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
        return "indexed" if chunks else "empty"

    def remove(self, rel_path: str) -> None:
        self._store.delete_note(rel_path)
        self._manifest.delete(rel_path)

    def sync(self) -> SyncReport:
        report = SyncReport()
        seen: set[str] = set()
        for abs_path in self.iter_note_paths():
            rel = abs_path.relative_to(self._s.vault_path).as_posix()
            seen.add(rel)
            try:
                status = self.index_file(abs_path)
            except Exception as exc:  # una nota rota no debe parar el sync; se registra y reporta
                log.exception("Fallo indexando %s", rel)
                report.failed.append((rel, repr(exc)))
                continue
            if status == "indexed":
                report.indexed += 1
                log.info("indexada: %s", rel)
            elif status == "empty":
                report.empty += 1
            else:
                report.unchanged += 1
        for gone in self._manifest.paths() - seen:
            self.remove(gone)
            report.deleted += 1
        return report
