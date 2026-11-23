from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
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
# 1: los enlaces `[[carpeta/Nota]]` conservan la carpeta en el payload.
LINKS_VERSION = 1


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
        def failed(exc: OSError) -> None:
            raise exc

        for root, dirs, files in os.walk(self._s.vault_path, onerror=failed):
            # Poda en sitio: no se entra en node_modules, .obsidian, _conceptos...
            dirs[:] = sorted(d for d in dirs if d not in self._s.exclude_dirs)
            for f in sorted(files):
                path = Path(root) / f
                if f.lower().endswith(".md") and not self._s.is_excluded(self._rel(path)):
                    yield path

    def index_file(self, abs_path: Path) -> Status:
        status = self._publish(abs_path)
        path = self._rel(abs_path)
        if self._manifest.pending_cleanup(path):
            with self._manifest.writing():
                generation = self._manifest.pending_cleanup(path)
                if generation:
                    self._store.retire_versions(path, generation)
                    self._manifest.cleaned(path)
        return status

    def _publish(self, abs_path: Path) -> Status:
        # Parseo, embeddings y subida a Qdrant van fuera del cerrojo del manifest: los puntos
        # nuevos son invisibles (ninguna generación del manifest los nombra) hasta el commit,
        # y las búsquedas no esperan a la publicación.
        note = parse_note(abs_path, self._s.vault_path)
        # El hash incluye la huella de configuración: cambiar modelo o chunking reindexa todo.
        stamp = f"{note.content_hash}:{self._fingerprint}"
        if self._manifest.get(note.path) == stamp:
            # Conceptos y copias se refrescan siempre: es barato y evita reindexar al añadirlos.
            self._refresh_links(note.path, note.links)
            with self._manifest.writing():
                self._manifest.set_meta(note.path, note.concepts, note.body_hash)
            return "unchanged"
        chunks = (
            []
            if note.frontmatter.get("sin_texto") is True
            else chunk_note(note, self._s.chunk_max_chars, self._s.chunk_min_chars)
        )
        # Se embebe antes de borrar: si falla, los chunks anteriores siguen intactos.
        vectors = self._embedder.embed_documents([c.embed_text for c in chunks]) if chunks else []
        generation = uuid.uuid4()
        if chunks:
            chunks = [
                replace(c, id=str(uuid.uuid5(generation, c.id)), generation=str(generation))
                for c in chunks
            ]
            self._store.upsert_chunks(chunks, vectors)
        with self._manifest.writing():
            self._manifest.upsert(
                note.path, stamp, len(chunks), str(generation), links_version=LINKS_VERSION
            )
            self._manifest.set_meta(note.path, note.concepts, note.body_hash)
        return "indexed" if chunks else "empty"

    def _refresh_links(self, path: str, links: tuple[str, ...]) -> None:
        """Índices anteriores: corrige solo el payload de enlaces con carpeta, sin re-embeber."""
        if self._manifest.links_version(path) >= LINKS_VERSION:
            return
        if any("/" in target for target in links):
            self._store.update_links(path, links)
        self._manifest.set_links_version(path, LINKS_VERSION)

    def is_indexed(self, rel_path: str) -> bool:
        return self._manifest.get(rel_path) is not None

    def remove(self, rel_path: str) -> None:
        with self._manifest.writing():
            self._store.delete_note(rel_path)
            self._manifest.delete(rel_path)

    def sync(self, on_progress: Callable[[int, int, str], None] | None = None) -> SyncReport:
        report = SyncReport()
        seen: set[str] = set()
        try:
            paths = list(self.iter_note_paths())
        except OSError as exc:
            report.failed.append((".", str(exc)))
            return report
        if not paths and self._manifest.paths():
            report.failed.append(
                (".", "Recorrido vacío con notas indexadas; se conserva el índice.")
            )
            return report
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
        if not report.failed:
            self._manifest.set_value("last_sync", self._now().isoformat())
        return report
