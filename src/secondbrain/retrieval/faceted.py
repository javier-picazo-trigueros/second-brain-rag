"""Búsqueda con filtros y facetas.

Filtros: O dentro de cada faceta (varias asignaturas = cualquiera de ellas) e Y entre facetas
(asignatura Y curso Y etiqueta). Se traducen a las rutas permitidas (`only_paths`) de la búsqueda.

Facetas: recuento por asignatura, curso y etiqueta sobre las mejores notas candidatas SIN filtrar,
para que el usuario vea cuántas habría si cambiara un filtro.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from secondbrain.retrieval.catalog import Catalog
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.subjects import norm

MAX_TAG_FACETS = 30
FACET_CANDIDATES = 20  # notas candidatas sobre las que se cuentan las facetas


class Searcher(Protocol):
    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult: ...


def _clean(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v.strip() for v in values if v.strip()))


@dataclass(frozen=True, slots=True)
class Filters:
    asignaturas: tuple[str, ...] = ()
    cursos: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("asignaturas", "cursos", "tags"):
            object.__setattr__(self, name, _clean(getattr(self, name)))

    @property
    def active(self) -> bool:
        return bool(self.asignaturas or self.cursos or self.tags)


@dataclass(frozen=True, slots=True)
class FacetCount:
    value: str
    count: int


@dataclass(frozen=True, slots=True)
class Facets:
    asignaturas: list[FacetCount] = field(default_factory=list)
    cursos: list[FacetCount] = field(default_factory=list)
    tags: list[FacetCount] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FacetedResult:
    result: SearchResult
    facets: Facets


def _ranked(
    counts: dict[str, int], selected: Sequence[str], limit: int | None = None
) -> list[FacetCount]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    chosen = ordered if limit is None else ordered[:limit]
    present = {value for value, _ in chosen}
    chosen.extend((value, 0) for value in selected if value not in present)  # se pueden desmarcar
    return [FacetCount(value, count) for value, count in chosen]


class FacetedSearch:
    def __init__(self, searcher: Searcher, catalog: Catalog) -> None:
        self._searcher = searcher
        self._catalog = catalog

    def search(self, query: str, k: int, *, with_graph: bool, filters: Filters) -> FacetedResult:
        if not filters.active:
            full = self._searcher.search(query, FACET_CANDIDATES, with_graph=with_graph)
            shown = SearchResult(full.notes[:k], full.related, full.top_similarity)
            return FacetedResult(shown, self._facets(full.notes, filters))

        candidates = self._searcher.search(query, FACET_CANDIDATES, with_graph=False)
        facets = self._facets(candidates.notes, filters)
        allowed = self._allowed(filters)
        if not allowed:
            return FacetedResult(SearchResult([], [], candidates.top_similarity), facets)
        result = self._searcher.search(query, k, with_graph=with_graph, only_paths=sorted(allowed))
        return FacetedResult(result, facets)

    # --- filtros ------------------------------------------------------------------------------

    def _allowed(self, filters: Filters) -> set[str]:
        index = self._catalog.subject_index()
        groups: list[set[str]] = []
        if filters.asignaturas:
            found = set()
            for name in filters.asignaturas:
                subject = index.by_name(name)
                if subject is not None:
                    found.update(index.notes_of(subject))
            groups.append(found)
        if filters.cursos:
            wanted = {norm(c) for c in filters.cursos}
            groups.append(
                {p for p in self._catalog.paths() if norm(self._catalog.course(p) or "") in wanted}
            )
        if filters.tags:
            wanted = {t.casefold() for t in filters.tags}
            groups.append(
                {
                    path
                    for path, tags in self._catalog.note_tags().items()
                    if wanted & {t.casefold() for t in tags}
                }
            )
        allowed = groups[0]
        for group in groups[1:]:
            allowed = allowed & group
        return allowed

    # --- facetas ------------------------------------------------------------------------------

    def _facets(self, notes: Sequence[NoteHit], filters: Filters) -> Facets:
        subjects: dict[str, int] = {}
        courses: dict[str, int] = {}
        tags: dict[str, int] = {}
        for note in notes:
            name = self._catalog.subject_name(note.path)
            if name:
                subjects[name] = subjects.get(name, 0) + 1
            course = self._catalog.course(note.path)
            if course:
                courses[course] = courses.get(course, 0) + 1
            first = note.chunks[0].payload if note.chunks else {}
            for tag in dict.fromkeys(str(t) for t in (first.get("tags") or [])):
                tags[tag] = tags.get(tag, 0) + 1
        return Facets(
            asignaturas=_ranked(subjects, filters.asignaturas),
            cursos=_ranked(courses, filters.cursos),
            tags=_ranked(tags, filters.tags, MAX_TAG_FACETS),
        )
