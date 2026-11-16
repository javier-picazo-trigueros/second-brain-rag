"""Dobles de prueba para el embedder y el store: los tests unitarios no usan Ollama ni Qdrant."""

from __future__ import annotations

from secondbrain.domain import Chunk

Events = list[tuple[str, str]]


class FakeEmbedder:
    def __init__(self, events: Events | None = None, fail_on: str | None = None) -> None:
        self.events: Events = events if events is not None else []
        self.fail_on = fail_on
        self.embedded: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise RuntimeError(f"fallo simulado al embeber {self.fail_on!r}")
        self.events.append(("embed", str(len(texts))))
        self.embedded.extend(texts)
        return [[float(len(t)), 0.0, 1.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 0.0, 1.0]

    def dimension(self) -> int:
        return 3


class FakeStore:
    def __init__(self, events: Events | None = None) -> None:
        self.events: Events = events if events is not None else []
        self.chunks: dict[str, list[Chunk]] = {}

    def upsert_chunks(self, chunks: list[Chunk], dense: list[list[float]]) -> None:
        assert len(chunks) == len(dense)
        for c in chunks:
            self.events.append(("upsert", c.note_path))
            self.chunks.setdefault(c.note_path, []).append(c)

    def delete_note(self, note_path: str) -> None:
        self.events.append(("delete", note_path))
        self.chunks.pop(note_path, None)

    @property
    def notes(self) -> set[str]:
        return set(self.chunks)

    def count(self) -> int:
        return sum(len(v) for v in self.chunks.values())
