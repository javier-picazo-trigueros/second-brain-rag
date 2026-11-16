"""Preguntas de visión general: en vez de buscar fragmentos, se resumen las notas de una
asignatura o de un tema con su `resumen`, sus conceptos y los apartados que contienen."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any, Protocol

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import HybridRetriever, NoteHit, SearchResult, canonical_key
from secondbrain.retrieval.intent import detect_intent
from secondbrain.retrieval.subjects import (
    SubjectIndex,
    SubjectSpec,
    load_aliases,
    norm,
    subject_of,
)
from secondbrain.store.manifest import Manifest

_COURSE = re.compile(r"^\d+º$")
_EXERCISE = re.compile(
    r"\b(?:exercis\w*|ejercicio\w*|solution|solucion\w*|taller|practic\w*|lab\w*|examen|test)\b"
)
_NO_SUMMARY = "Sin resumen."
_HEADING_LEVELS = 2  # solo los dos primeros niveles de cada encabezado


class OutlineSource(Protocol):
    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]: ...


class Searcher(Protocol):
    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult: ...


def _natural_key(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", norm(text))]


def _course(path: str) -> str | None:
    first = path.split("/")[0]
    return first if _COURSE.match(first) else None


class OverviewBuilder:
    def __init__(self, settings: Settings, store: OutlineSource, manifest: Manifest) -> None:
        self._s = settings
        self._store = store
        self._manifest = manifest

    def build(
        self, notes: Sequence[str], headings: int, max_chars: int | None = None
    ) -> SearchResult:
        """Una «nota» sintética por cada nota real, sin copias exactas y dentro del tope."""
        reps, copies = self._collapse(notes)
        chosen = self._choose(reps)
        outline = self._store.outline(chosen)
        concepts = self._manifest.note_concepts()
        counts = self._manifest.chunk_counts()
        hits: list[NoteHit] = []
        for i, path in enumerate(chosen):
            own = sorted(
                (p for p in outline if p["note_path"] == path), key=lambda p: p["position"]
            )
            text = self._text(own, concepts.get(path, ()), headings)
            if max_chars is not None and len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
            payload: dict[str, Any] = {
                "note_path": path,
                "text": text,
                "asignatura": subject_of(path),
                "curso": _course(path),
                "heading_path": None,
                "page": None,
                "resumen": own[0].get("resumen") if own else None,
            }
            score = 1.0 - i / 1000
            hits.append(
                NoteHit(
                    path=path,
                    title=PurePosixPath(path).stem,
                    score=score,
                    raw_score=score,
                    chunks=(Hit(score, payload),),
                    also_in=copies.get(path, ()),
                    n_chunks=counts.get(path, 1),
                )
            )
        return SearchResult(hits, [], None, mode="overview")

    def _collapse(self, notes: Sequence[str]) -> tuple[list[str], dict[str, tuple[str, ...]]]:
        wanted = set(notes)
        canonical: dict[str, str] = {}
        others: dict[str, tuple[str, ...]] = {}
        for group in self._manifest.duplicate_groups():
            rep = min(group, key=canonical_key)
            others[rep] = tuple(p for p in group if p != rep)
            for path in group:
                canonical[path] = rep
        reps = dict.fromkeys(canonical.get(p, p) for p in notes if p in wanted)
        return list(reps), others

    def _choose(self, reps: list[str]) -> list[str]:
        """Si sobran notas, primero la teoría y luego los ejercicios; siempre en orden natural."""

        def title(path: str) -> str:
            return PurePosixPath(path).stem

        ranked = sorted(
            reps, key=lambda p: (bool(_EXERCISE.search(norm(title(p)))), _natural_key(title(p)))
        )
        kept = ranked[: self._s.overview_max_notes]
        return sorted(kept, key=lambda p: _natural_key(title(p)))

    @staticmethod
    def _text(own: list[dict[str, Any]], concepts: Sequence[str], headings: int) -> str:
        resumen = next((str(p["resumen"]) for p in own if p.get("resumen")), _NO_SUMMARY)
        lines = [f"Resumen: {resumen}"]
        if concepts:
            lines.append(f"Conceptos: {', '.join(concepts)}")
        if headings > 0:
            seen: dict[str, None] = {}
            for p in own:
                parts = str(p.get("heading_path") or "").split(" > ")[:_HEADING_LEVELS]
                for part in parts:
                    if part:
                        seen.setdefault(part)
            if seen:
                lines.append(f"Apartados: {'; '.join(list(seen)[:headings])}")
        return "\n".join(lines)


class IntentRetriever:
    """Decide por pregunta: visión general de una asignatura o tema, o búsqueda híbrida normal."""

    def __init__(
        self,
        settings: Settings,
        base: HybridRetriever | Searcher,
        store: OutlineSource,
        manifest: Manifest,
        aliases: Mapping[str, SubjectSpec] | None = None,
    ) -> None:
        self._s = settings
        self._base = base
        self._manifest = manifest
        self._builder = OverviewBuilder(settings, store, manifest)
        self._aliases = load_aliases(settings.aliases_path) if aliases is None else aliases
        self._index_key: int | None = None
        self._index: SubjectIndex | None = None

    def _subjects(self) -> SubjectIndex:
        paths = self._manifest.paths()
        key = hash(frozenset(paths))
        if self._index is None or key != self._index_key:
            self._index = SubjectIndex(paths, self._aliases)
            self._index_key = key
        return self._index

    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult:
        index = self._subjects()
        intent = detect_intent(query, index)
        if intent.subject is not None and intent.kind != "search":
            if intent.topic is not None:
                notes = index.topic_notes(intent.subject, intent.topic)
                if notes:
                    return self._builder.build(notes, self._s.overview_headings_topic)
            else:
                return self._builder.build(
                    index.notes_of(intent.subject),
                    self._s.overview_headings_subject,
                    self._s.overview_text_chars,
                )
        return self._base.search(query, k, with_graph=with_graph)
