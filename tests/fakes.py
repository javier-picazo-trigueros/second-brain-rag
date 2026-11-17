"""Dobles de prueba para el embedder y el store: los tests unitarios no usan Ollama ni Qdrant."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from secondbrain.answer.llm import Delta, Finished, LLMError, Message
from secondbrain.domain import Chunk, Hit
from secondbrain.retrieval.hybrid import SearchResult

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

    def ensure_collection(self) -> None:
        self.events.append(("ensure_collection", ""))

    def search(
        self,
        query: str,
        query_dense: list[float],
        limit: int = 8,
        prefetch: int = 40,
        only_paths: Sequence[str] | None = None,
    ) -> list[Hit]:
        terms = [t for t in query.lower().split() if t]
        hits: list[Hit] = []
        for chunks in self.chunks.values():
            for c in chunks:
                if only_paths is not None and c.note_path not in only_paths:
                    continue
                score = float(sum(c.text.lower().count(t) for t in terms))
                if score > 0:
                    payload = {
                        "note_path": c.note_path,
                        "note_title": c.note_title,
                        "heading_path": " > ".join(c.heading_path),
                        "position": c.position,
                        "page": c.page,
                        "text": c.text,
                        "tags": list(c.tags),
                        "asignatura": c.asignatura,
                        "curso": c.curso,
                        "resumen": c.resumen,
                    }
                    hits.append(Hit(score=score, payload=payload))
        return sorted(hits, key=lambda h: -h.score)[:limit]

    def search_note(self, note_path: str, query_dense: list[float], limit: int = 1) -> list[Hit]:
        hits = [
            Hit(
                1.0,
                {
                    "note_path": c.note_path,
                    "heading_path": " > ".join(c.heading_path),
                    "page": c.page,
                    "text": c.text,
                    "resumen": c.resumen,
                },
            )
            for c in self.chunks.get(note_path, [])
        ]
        return hits[:limit]

    @property
    def notes(self) -> set[str]:
        return set(self.chunks)

    def dense_top(self, query_dense: list[float]) -> float | None:
        return 0.5 if self.chunks else None

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        return {path: tuple(chunks[0].tags) for path, chunks in self.chunks.items() if chunks}

    def note_links(self) -> dict[str, tuple[str, ...]]:
        return {path: tuple(chunks[0].links) for path, chunks in self.chunks.items() if chunks}

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {
                "note_path": c.note_path,
                "note_title": c.note_title,
                "heading_path": " > ".join(c.heading_path),
                "position": c.position,
                "page": c.page,
                "text": c.text,
                "asignatura": c.asignatura,
                "curso": c.curso,
                "resumen": c.resumen,
            }
            for p in paths
            for c in self.chunks.get(p, [])
        ]

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {
                "note_path": c.note_path,
                "position": c.position,
                "heading_path": " > ".join(c.heading_path),
                "resumen": c.resumen,
            }
            for p in paths
            for c in self.chunks.get(p, [])
        ]

    def dense_notes(
        self, query_dense: list[float], limit: int = 100, only_paths: Sequence[str] | None = None
    ) -> dict[str, float]:
        return {p: 0.5 for p in self.chunks if only_paths is None or p in only_paths}

    def count(self) -> int:
        return sum(len(v) for v in self.chunks.values())


class ScriptedStore:
    """Store con resultados predefinidos, para probar la lógica de ranking sin Qdrant."""

    def __init__(
        self,
        hits: list[Hit],
        best: dict[str, Hit] | None = None,
        dense: float | None = 0.6,
        cosines: dict[str, float] | None = None,
    ) -> None:
        self.hits = hits
        self.dense = dense
        self.cosines = cosines or {}
        self.last_only_paths: Sequence[str] | None = None
        self.best = best or {}
        self.last_search: dict[str, object] = {}
        self.note_calls: list[str] = []

    def ensure_collection(self) -> None: ...

    def upsert_chunks(self, chunks: list[Chunk], dense: list[list[float]]) -> None: ...

    def delete_note(self, note_path: str) -> None: ...

    def search(
        self,
        query: str,
        query_dense: list[float],
        limit: int = 8,
        prefetch: int = 40,
        only_paths: Sequence[str] | None = None,
    ) -> list[Hit]:
        self.last_search = {"query": query, "limit": limit, "prefetch": prefetch}
        self.last_only_paths = only_paths
        return self.hits[:limit]

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        return {}

    def note_links(self) -> dict[str, tuple[str, ...]]:
        return {}

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return []

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return []

    def dense_notes(
        self, query_dense: list[float], limit: int = 100, only_paths: Sequence[str] | None = None
    ) -> dict[str, float]:
        return dict(self.cosines)

    def search_note(self, note_path: str, query_dense: list[float], limit: int = 1) -> list[Hit]:
        self.note_calls.append(note_path)
        return [self.best[note_path]] if note_path in self.best else []

    def dense_top(self, query_dense: list[float]) -> float | None:
        return self.dense

    def count(self) -> int:
        return len(self.hits)


FINISHED = Finished(
    prompt_tokens=900, completion_tokens=50, load_ms=0.0, prompt_eval_ms=400.0,
    eval_ms=1000.0, truncated=False,
)  # fmt: skip


class FakeRetriever:
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult:
        self.calls.append((query, k))
        return self.result


class ScriptedLLM:
    def __init__(
        self,
        deltas: Sequence[str],
        finished: Finished | None = FINISHED,
        fail_after: int | None = None,
    ) -> None:
        self.deltas = list(deltas)
        self.finished = finished
        self.fail_after = fail_after
        self.messages: list[Message] = []
        self.calls = 0

    def stream_chat(self, messages: Sequence[Message]) -> Iterator[Delta | Finished]:
        self.calls += 1
        self.messages = list(messages)
        for i, text in enumerate(self.deltas):
            if self.fail_after is not None and i == self.fail_after:
                raise LLMError("Ollama no responde en http://x: arráncalo con `ollama serve`.")
            yield Delta(text)
        if self.fail_after is not None and self.fail_after >= len(self.deltas):
            raise LLMError("Ollama no responde en http://x: arráncalo con `ollama serve`.")
        if self.finished is not None:
            yield self.finished


class Tick:
    """Reloj que avanza 0,1 s cada vez que se lee: tiempos deterministas."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.1
        return self.now
