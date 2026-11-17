from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.catalog import Catalog
from secondbrain.retrieval.faceted import FacetedSearch, Filters
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.subjects import SubjectSpec
from secondbrain.store.manifest import Manifest

NOTES = {
    "3º/Redes/Tema 1.md": ["red", "ip"],
    "3º/Redes/Tema 2.md": ["red"],
    "3º/DM/DM - Unit 1.md": ["datos"],
    "3º/IA II/DM - Unit 0.md": ["datos", "intro"],  # va a Data Mining por el include
    "3º/IA II/AIII - Unit 1.md": ["ia"],
    "4º/TFG/Memoria.md": [],
}
ALIASES = {
    "Data Mining": SubjectSpec(aliases=("data mining",), folders=("DM",), include=("ia ii dm",))
}


class TagStore:
    def __init__(self) -> None:
        self.calls = 0

    def note_links(self) -> dict[str, tuple[str, ...]]:
        return {}

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        self.calls += 1
        return {p: tuple(t) for p, t in NOTES.items()}


class RecordingSearcher:
    """Devuelve todas las notas permitidas (o todas) y apunta cómo se la llamó."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult:
        self.calls.append(
            {"k": k, "graph": with_graph, "only": None if only_paths is None else set(only_paths)}
        )
        allowed = NOTES if only_paths is None else [p for p in NOTES if p in only_paths]
        notes = [
            NoteHit(
                p,
                Path(p).stem,
                1.0 - i / 10,
                1.0,
                (Hit(0.5, {"note_path": p, "tags": NOTES[p], "text": "t"}),),
                (),
                3,
            )
            for i, p in enumerate(allowed)
        ][:k]
        return SearchResult(notes, [], 0.7)


@pytest.fixture
def parts(tmp_path: Path) -> Iterator[tuple[FacetedSearch, RecordingSearcher, TagStore]]:
    manifest = Manifest(tmp_path / "m.sqlite")
    for p in NOTES:
        manifest.upsert(p, "h", 3)
        manifest.set_meta(p, (), None)
    store, searcher = TagStore(), RecordingSearcher()
    settings = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    catalog = Catalog(settings, manifest, store, aliases=ALIASES)
    yield FacetedSearch(searcher, catalog), searcher, store
    manifest.close()


def names(result: Any) -> list[str]:
    return [n.path for n in result.result.notes]


def values(facet: list[Any]) -> dict[str, int]:
    return {f.value: f.count for f in facet}


def test_without_filters_it_is_one_unfiltered_search(parts: Any) -> None:
    search, searcher, _ = parts
    out = search.search("redes", 5, with_graph=True, filters=Filters())
    assert len(searcher.calls) == 1 and searcher.calls[0]["only"] is None
    assert len(out.result.notes) == 5


def test_facets_are_counted_over_the_top_candidates_with_canonical_names(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 20, with_graph=False, filters=Filters())
    assert values(out.facets.asignaturas) == {
        "Redes": 2,
        "Data Mining": 2,  # DM - Unit 1 y la unidad que estaba guardada en IA II
        "IA II": 1,
        "TFG": 1,
    }
    assert values(out.facets.cursos) == {"3º": 5, "4º": 1}
    assert values(out.facets.tags) == {"red": 2, "datos": 2, "ip": 1, "intro": 1, "ia": 1}


def test_facets_are_sorted_by_count_then_name(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 20, with_graph=False, filters=Filters())
    assert [f.value for f in out.facets.tags][:2] == ["datos", "red"]  # empate: por nombre


def test_a_subject_filter_restricts_the_search_to_that_subjects_notes(parts: Any) -> None:
    search, searcher, _ = parts
    out = search.search("x", 5, with_graph=False, filters=Filters(asignaturas=("Data Mining",)))
    assert set(names(out)) == {"3º/DM/DM - Unit 1.md", "3º/IA II/DM - Unit 0.md"}
    assert searcher.calls[-1]["only"] == set(names(out))


def test_values_inside_a_facet_are_ored(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 9, with_graph=False, filters=Filters(asignaturas=("Redes", "TFG")))
    assert set(names(out)) == {"3º/Redes/Tema 1.md", "3º/Redes/Tema 2.md", "4º/TFG/Memoria.md"}


def test_different_facets_are_anded(parts: Any) -> None:
    search, _, _ = parts
    out = search.search(
        "x", 9, with_graph=False, filters=Filters(asignaturas=("Redes",), tags=("ip",))
    )
    assert names(out) == ["3º/Redes/Tema 1.md"]
    out = search.search("x", 9, with_graph=False, filters=Filters(cursos=("4º",), tags=("ip",)))
    assert names(out) == []


def test_course_and_tag_filters(parts: Any) -> None:
    search, _, _ = parts
    assert set(names(search.search("x", 9, with_graph=False, filters=Filters(cursos=("4º",))))) == {
        "4º/TFG/Memoria.md"
    }
    assert set(
        names(search.search("x", 9, with_graph=False, filters=Filters(tags=("datos", "ia"))))
    ) == {
        "3º/DM/DM - Unit 1.md",
        "3º/IA II/DM - Unit 0.md",
        "3º/IA II/AIII - Unit 1.md",
    }


def test_an_unknown_subject_matches_nothing(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 5, with_graph=False, filters=Filters(asignaturas=("Inventada",)))
    assert out.result.notes == []


def test_filters_ignore_case_and_accents_in_names(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 5, with_graph=False, filters=Filters(asignaturas=("data MINING",)))
    assert len(out.result.notes) == 2


def test_with_filters_facets_still_come_from_the_unfiltered_candidates(parts: Any) -> None:
    search, searcher, _ = parts
    out = search.search("x", 5, with_graph=False, filters=Filters(asignaturas=("Redes",)))
    assert len(searcher.calls) == 2
    assert (
        searcher.calls[0]["only"] is None
        and searcher.calls[0]["k"] == 20
        and searcher.calls[0]["graph"] is False
    )
    assert (
        values(out.facets.asignaturas)["Data Mining"] == 2
    )  # lo que habría si se cambiara el filtro


def test_selected_values_stay_listed_even_with_a_zero_count(parts: Any) -> None:
    search, _, _ = parts
    out = search.search("x", 5, with_graph=False, filters=Filters(tags=("fantasma",)))
    assert values(out.facets.tags)["fantasma"] == 0


def test_the_number_of_tag_values_is_capped(parts: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    search, _, _ = parts
    monkeypatch.setattr("secondbrain.retrieval.faceted.MAX_TAG_FACETS", 2)
    assert len(search.search("x", 20, with_graph=False, filters=Filters()).facets.tags) == 2


def test_the_catalog_reads_tags_once_until_the_index_changes(parts: Any, tmp_path: Path) -> None:
    search, _, store = parts
    for _ in range(3):
        search.search("x", 5, with_graph=False, filters=Filters(tags=("red",)))
    assert store.calls == 1


def test_filters_normalise_their_lists() -> None:
    f = Filters(asignaturas=("A", "A", " b "), cursos=(), tags=("t",))
    assert f.asignaturas == ("A", "b") and f.active is True
    assert Filters().active is False
