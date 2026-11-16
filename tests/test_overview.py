from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import SearchResult
from secondbrain.retrieval.overview import IntentRetriever, OverviewBuilder
from secondbrain.store.manifest import Manifest


class OutlineStore:
    """Solo lo que la ruta de visión general le pide al store: el esquema de las notas."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.asked: list[Sequence[str]] = []

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        self.asked.append(list(paths))
        return [p for p in self.payloads if p["note_path"] in paths]


def chunk(
    path: str, position: int, heading: str, resumen: str | None = "Resumen de la nota."
) -> dict[str, Any]:
    return {"note_path": path, "position": position, "heading_path": heading, "resumen": resumen}


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "m.sqlite")
    yield m
    m.close()


def settings(tmp_path: Path, **over: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **over)  # type: ignore[call-arg]


def add(
    manifest: Manifest, path: str, concepts: Sequence[str] = (), group: str | None = None
) -> None:
    manifest.upsert(path, "h", 3)
    manifest.set_meta(path, tuple(concepts), group)


def test_each_note_becomes_one_synthetic_chunk(tmp_path: Path, manifest: Manifest) -> None:
    path = "3º/DM/DM - Unit 1 - Intro.md"
    add(manifest, path, ["clustering", "kdd"])
    store = OutlineStore(
        [
            chunk(path, 0, "Intro"),
            chunk(path, 1, "Intro > KDD"),
            chunk(path, 2, "Intro > KDD > Fases"),
        ]
    )
    result = OverviewBuilder(settings(tmp_path), store, manifest).build([path], headings=5)
    assert result.mode == "overview"
    (note,) = result.notes
    text = str(note.chunks[0].payload["text"])
    assert "Resumen de la nota." in text
    assert "clustering, kdd" in text
    assert "Intro; KDD" in text  # solo los dos primeros niveles, sin repetir
    assert note.path == path and note.title == "DM - Unit 1 - Intro"
    assert note.chunks[0].payload["asignatura"] == "DM"
    assert note.chunks[0].payload["curso"] == "3º"
    assert note.chunks[0].payload["page"] is None
    assert result.related == []


def test_notes_without_summary_still_appear(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/DM/Sin.md")
    store = OutlineStore([chunk("3º/DM/Sin.md", 0, "Tema", resumen=None)])
    (note,) = OverviewBuilder(settings(tmp_path), store, manifest).build(["3º/DM/Sin.md"], 3).notes
    assert "Sin resumen" in str(note.chunks[0].payload["text"])


def test_headings_are_capped_and_ordered_by_position(tmp_path: Path, manifest: Manifest) -> None:
    path = "3º/DM/A.md"
    add(manifest, path)
    store = OutlineStore([chunk(path, i, f"H{i}") for i in (3, 1, 2, 0)])
    (note,) = OverviewBuilder(settings(tmp_path), store, manifest).build([path], headings=2).notes
    text = str(note.chunks[0].payload["text"])
    assert "H0; H1" in text and "H2" not in text


def test_headings_can_be_left_out(tmp_path: Path, manifest: Manifest) -> None:
    path = "3º/DM/A.md"
    add(manifest, path)
    (note,) = (
        OverviewBuilder(settings(tmp_path), OutlineStore([chunk(path, 0, "Tema")]), manifest)
        .build([path], 0)
        .notes
    )
    assert "Tema" not in str(note.chunks[0].payload["text"])


def test_exact_copies_collapse_to_the_canonical_path(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/DM/A.md", group="g")
    add(manifest, "3º/IA II/A (1).md", group="g")
    store = OutlineStore([chunk("3º/DM/A.md", 0, "T"), chunk("3º/IA II/A (1).md", 0, "T")])
    result = OverviewBuilder(settings(tmp_path), store, manifest).build(
        ["3º/DM/A.md", "3º/IA II/A (1).md"], 0
    )
    assert [n.path for n in result.notes] == ["3º/DM/A.md"]
    assert result.notes[0].also_in == ("3º/IA II/A (1).md",)


def test_natural_order_and_theory_before_exercises_under_the_cap(
    tmp_path: Path, manifest: Manifest
) -> None:
    paths = [
        "3º/DM/DM - Unit 10 - Final.md",
        "3º/DM/DM - Unit 2 - Datos.md",
        "3º/DM/DM - Unit 2 - exercises 1 - solution.md",
        "3º/DM/DM - Unit 1 - Intro.md",
    ]
    for p in paths:
        add(manifest, p)
    store = OutlineStore([chunk(p, 0, "T") for p in paths])
    result = OverviewBuilder(settings(tmp_path, overview_max_notes=3), store, manifest).build(
        paths, 0
    )
    assert [n.title for n in result.notes] == [
        "DM - Unit 1 - Intro",
        "DM - Unit 2 - Datos",
        "DM - Unit 10 - Final",
    ]


# --- enrutador ------------------------------------------------------------------------------


class MarkerRetriever:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult:
        self.calls.append(query)
        return SearchResult([], [], 0.9)


@pytest.fixture
def routed(
    tmp_path: Path, manifest: Manifest
) -> tuple[IntentRetriever, MarkerRetriever, OutlineStore]:
    paths = [
        "3º/Discretas/Tema 5 Grafos.md",
        "3º/Discretas/Tema 4 Números.md",
        "3º/DM/DM - Unit 1 - Intro.md",
    ]
    for p in paths:
        add(manifest, p)
    store = OutlineStore([chunk(p, 0, "Tema") for p in paths])
    base = MarkerRetriever()
    router = IntentRetriever(settings(tmp_path), base, store, manifest, aliases={})
    return router, base, store


def test_normal_questions_go_to_the_hybrid_retriever(routed: Any) -> None:
    router, base, store = routed
    router.search("¿Qué es un grafo bipartito?", k=5)
    assert base.calls == ["¿Qué es un grafo bipartito?"] and store.asked == []


def test_subject_overview_lists_the_subject_notes(routed: Any) -> None:
    router, base, store = routed
    result = router.search("¿De qué trata la asignatura de discretas?", k=5)
    assert result.mode == "overview" and base.calls == []
    assert {n.path for n in result.notes} == {
        "3º/Discretas/Tema 5 Grafos.md",
        "3º/Discretas/Tema 4 Números.md",
    }


def test_topic_overview_keeps_only_that_topic(routed: Any) -> None:
    router, base, _ = routed
    result = router.search("¿Qué se da en el tema 5 de discretas?", k=5)
    assert [n.path for n in result.notes] == ["3º/Discretas/Tema 5 Grafos.md"]


def test_topic_with_no_notes_falls_back_to_search(routed: Any) -> None:
    router, base, _ = routed
    result = router.search("¿Qué se da en el tema 9 de discretas?", k=5)
    assert result.mode == "search" and len(base.calls) == 1


def test_new_notes_are_seen_after_the_index_changes(routed: Any, manifest: Manifest) -> None:
    router, _, store = routed
    assert router.search("¿De qué trata la asignatura de redes?", k=5).mode == "search"
    add(manifest, "3º/Redes/Tema 1.md")
    store.payloads.append(chunk("3º/Redes/Tema 1.md", 0, "IP"))
    assert router.search("¿De qué trata la asignatura de redes?", k=5).mode == "overview"


def test_hit_type_is_a_plain_hit(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/DM/A.md")
    store = OutlineStore([chunk("3º/DM/A.md", 0, "T")])
    (note,) = OverviewBuilder(settings(tmp_path), store, manifest).build(["3º/DM/A.md"], 0).notes
    assert isinstance(note.chunks[0], Hit)
