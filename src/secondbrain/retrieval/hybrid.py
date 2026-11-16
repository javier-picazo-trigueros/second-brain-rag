from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.protocols import Embedder, Store
from secondbrain.retrieval.graph import ConceptGraph
from secondbrain.store.manifest import Manifest

# Sufijos típicos de las copias: "nota (1)", "nota - copia", "nota copy (2)".
_COPY_SUFFIX = re.compile(r"\s*(\(\d+\)|[-_ ]*copia( \(\d+\))?|[-_ ]*copy( \(\d+\))?)\s*$", re.I)
_SNIPPET_CHARS = 300
_COSINE_LOOKUPS = 20  # notas del ranking cuyo coseno se pide aparte si falta en el denso


@dataclass(frozen=True, slots=True)
class NoteHit:
    """Una nota del ranking: sus mejores chunks y la puntuación tras los ajustes."""

    path: str
    title: str
    score: float  # raw_score tras rebaja y penalización por longitud: la que ordena
    raw_score: float  # mejor score de fusión (RRF) de sus chunks
    chunks: tuple[Hit, ...]
    also_in: tuple[str, ...]  # copias exactas en otras rutas
    n_chunks: int
    cosine: float | None = None  # coseno denso de su mejor chunk (None si no se conoce)


@dataclass(frozen=True, slots=True)
class RelatedNote:
    """Nota relacionada por el grafo de conceptos. No forma parte del ranking."""

    path: str
    score: float
    via: tuple[str, ...]
    seeds: tuple[str, ...]
    resumen: str | None
    heading_path: str | None
    page: int | None
    snippet: str | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    notes: list[NoteHit]
    related: list[RelatedNote]
    # Coseno del mejor chunk: mide cuánto se parece la consulta al vault (el RRF no está calibrado).
    top_similarity: float | None = None
    mode: str = "search"  # "overview": resumen de una asignatura o tema, no fragmentos


def canonical_key(path: str) -> tuple[bool, int, str]:
    has_suffix = bool(_COPY_SUFFIX.search(PurePosixPath(path).stem))
    return (has_suffix, len(path), path)


class HybridRetriever:
    """Denso + BM25 (fusión RRF en Qdrant) + ajustes en cliente + notas relacionadas por grafo."""

    def __init__(
        self, settings: Settings, embedder: Embedder, store: Store, manifest: Manifest
    ) -> None:
        self._s = settings
        self._embedder = embedder
        self._store = store
        self._manifest = manifest

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult:
        dense = self._embedder.embed_query(query)
        hits = self._store.search(
            query,
            dense,
            limit=self._s.candidate_limit,
            prefetch=self._s.prefetch_limit,
            only_paths=only_paths,
        )
        cosines = self._store.dense_notes(dense, self._s.prefetch_limit, only_paths)
        similarity = max(cosines.values()) if cosines else self._store.dense_top(dense)
        if not hits:
            return SearchResult([], [], similarity)
        canonical, copies = self._copy_index()
        ranked = self._relevant(self._rank(hits, canonical, copies), cosines, dense)
        if not ranked:
            return SearchResult([], [], similarity)
        selected = self._select(ranked, k)
        related = self._related(selected, dense, canonical) if with_graph else []
        return SearchResult(selected, related, similarity)

    # --- ranking ------------------------------------------------------------------------------

    def _relevant(
        self, ranked: list[NoteHit], cosines: dict[str, float], dense: list[float]
    ) -> list[NoteHit]:
        """Descarta las notas poco parecidas a la consulta (coseno absoluto y relativo al mejor).

        El score RRF solo ordena: no distingue una nota relevante de una cualquiera que quedó
        primera en una de las dos ramas. El coseno denso de su mejor chunk sí.
        """
        with_cosine: list[NoteHit] = []
        for position, note in enumerate(ranked):
            known = [cosines[p] for p in (note.path, *note.also_in) if p in cosines]
            cosine = max(known) if known else None
            if cosine is None and position < _COSINE_LOOKUPS:
                best = self._store.search_note(note.path, dense, limit=1)
                cosine = best[0].score if best else None
            with_cosine.append(replace(note, cosine=cosine))
        values = [n.cosine for n in with_cosine if n.cosine is not None]
        if not values:
            # Con cosenos reales, una nota sin ninguno ni siquiera entró en el denso: no pasa.
            return [] if cosines else with_cosine
        floor = max(self._s.min_note_cosine, max(values) - self._s.cosine_margin)
        keep_unknown = not cosines  # sin cosenos (store de pruebas) no hay base para descartar
        return [
            n
            for n in with_cosine
            if (n.cosine is None and keep_unknown) or (n.cosine is not None and n.cosine >= floor)
        ]

    def _copy_index(self) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
        """Para cada nota con copias exactas: su ruta canónica y las demás ubicaciones."""
        canonical: dict[str, str] = {}
        others: dict[str, tuple[str, ...]] = {}
        for group in self._manifest.duplicate_groups():
            rep = min(group, key=canonical_key)
            others[rep] = tuple(p for p in group if p != rep)
            for path in group:
                canonical[path] = rep
        return canonical, others

    def _penalty(self, n_chunks: int) -> float:
        ratio = max(1.0, n_chunks / self._s.length_ref_chunks)
        return 1.0 + self._s.length_penalty_alpha * math.log2(ratio)

    def _rank(
        self, hits: list[Hit], canonical: dict[str, str], copies: dict[str, tuple[str, ...]]
    ) -> list[NoteHit]:
        by_note: dict[str, dict[str, list[Hit]]] = {}
        for h in hits:  # `hits` llega ordenado por score descendente
            path = str(h.payload["note_path"])
            rep = canonical.get(path, path)
            chunks = by_note.setdefault(rep, {}).setdefault(path, [])
            if len(chunks) < self._s.max_chunks_per_note:
                chunks.append(h)

        counts = self._manifest.chunk_counts()
        notes: list[NoteHit] = []
        for rep, members in by_note.items():
            shown = rep if rep in members else max(members, key=lambda m: members[m][0].score)
            raw = max(chunks[0].score for chunks in members.values())
            n_chunks = counts.get(rep, counts.get(shown, 0))
            score = raw * self._s.demotion_for(rep) / self._penalty(n_chunks)
            notes.append(
                NoteHit(
                    path=rep,
                    title=PurePosixPath(rep).stem,
                    score=score,
                    raw_score=raw,
                    chunks=tuple(members[shown]),
                    also_in=copies.get(rep, ()),
                    n_chunks=n_chunks,
                )
            )
        notes.sort(key=lambda n: (-n.score, n.path))
        return notes

    def _select(self, ranked: list[NoteHit], k: int) -> list[NoteHit]:
        """Top-k con cuota de notas grandes (libros): las que sobran solo rellenan huecos."""
        top = ranked[0].score
        selected: list[NoteHit] = []
        deferred: list[NoteHit] = []
        big = 0
        for note in ranked:
            if len(selected) >= k:
                break
            is_big = note.n_chunks >= self._s.big_note_chunks
            near_top = note.score >= self._s.quota_override_ratio * top
            if is_big and big >= self._s.big_note_quota and not near_top:
                deferred.append(note)
                continue
            selected.append(note)
            big += is_big
        selected.extend(deferred[: max(0, k - len(selected))])
        selected.sort(key=lambda n: (-n.score, n.path))
        return selected

    # --- grafo --------------------------------------------------------------------------------

    def _related(
        self, selected: list[NoteHit], dense: list[float], canonical: dict[str, str]
    ) -> list[RelatedNote]:
        if not selected or self._s.graph_budget == 0:
            return []
        shown = {n.path for n in selected}
        exclude = shown | {copy for n in selected for copy in n.also_in}
        graph = ConceptGraph.from_manifest(self._manifest)
        expanded = graph.expand(
            [(n.path, n.score) for n in selected],
            fanout_cap=self._s.graph_fanout_cap,
            budget=self._s.graph_budget * 3,  # margen: al colapsar copias se pierden algunas
            min_idf=self._s.graph_min_idf,
            exclude=exclude,
        )
        related: list[RelatedNote] = []
        seen = set(shown)
        for rel in expanded:
            rep = canonical.get(rel.path, rel.path)
            if rep in seen:
                continue
            seen.add(rep)
            best = self._store.search_note(rep, dense, limit=1)
            payload = best[0].payload if best else {}
            text = payload.get("text")
            related.append(
                RelatedNote(
                    path=rep,
                    score=rel.score,
                    via=rel.via,
                    seeds=rel.seeds,
                    resumen=payload.get("resumen"),
                    heading_path=payload.get("heading_path"),
                    page=payload.get("page"),
                    snippet=str(text)[:_SNIPPET_CHARS] if text else None,
                )
            )
            if len(related) >= self._s.graph_budget:
                break
        return related
