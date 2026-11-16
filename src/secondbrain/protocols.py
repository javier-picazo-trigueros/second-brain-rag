"""Contratos que el resto del código necesita de Ollama y Qdrant.

Permiten testear la lógica con fakes, sin servicios en marcha.
"""

from __future__ import annotations

from typing import Protocol

from secondbrain.domain import Chunk, Hit


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def dimension(self) -> int: ...


class Store(Protocol):
    def ensure_collection(self) -> None: ...

    def upsert_chunks(self, chunks: list[Chunk], dense: list[list[float]]) -> None: ...

    def delete_note(self, note_path: str) -> None: ...

    def search(
        self, query: str, query_dense: list[float], limit: int = 8, prefetch: int = 40
    ) -> list[Hit]: ...

    def search_note(
        self, note_path: str, query_dense: list[float], limit: int = 1
    ) -> list[Hit]: ...

    def count(self) -> int: ...
