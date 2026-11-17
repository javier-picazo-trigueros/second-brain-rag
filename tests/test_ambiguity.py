from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.overview import IntentRetriever
from secondbrain.retrieval.subjects import SubjectSpec
from secondbrain.store.manifest import Manifest

ALIASES = {
    "Matemática Discreta": SubjectSpec(aliases=("discreta",), folders=("DISCRETAS",)),
    "Cálculo": SubjectSpec(aliases=("calculo",), folders=("CALCULO",)),
}
GRAFOS = "1º/DISCRETAS/Tema 5 Teoría de grafos.md"
EULER = "2º/CALCULO/Tema 7 Método de Euler.md"
OTRO = "1º/DISCRETAS/Tema 2 Relaciones.md"


def hit(path: str, score: float) -> NoteHit:
    payload = {"note_path": path, "heading_path": "H", "page": 1, "text": "texto"}
    return NoteHit(path, path.rsplit("/", 1)[-1][:-3], score, score, (Hit(score, payload),), (), 5)


class Base:
    def __init__(self, notes: list[NoteHit]) -> None:
        self.notes = notes

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult:
        return SearchResult(self.notes, [], 0.8)


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "m.sqlite")
    for p in (GRAFOS, EULER, OTRO):
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    yield m
    m.close()


class NoChunks:
    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return []

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return []


def route(tmp_path: Path, manifest: Manifest, notes: list[NoteHit], question: str) -> SearchResult:
    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    router = IntentRetriever(s, Base(notes), NoChunks(), manifest, aliases=ALIASES)
    return router.search(question, k=5)


def test_close_sources_from_different_subjects_are_flagged_as_ambiguous(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path, manifest, [hit(GRAFOS, 0.9), hit(EULER, 0.8)], "dame la fórmula de Euler"
    )
    assert "AMBIGÜEDAD" in result.facts
    assert "Matemática Discreta" in result.facts and "Cálculo" in result.facts
    assert "Tema 5 Teoría de grafos" in result.facts and "Método de Euler" in result.facts
    assert "primera frase" in result.facts and "más relevante" in result.facts
    assert [n.path for n in result.notes] == [GRAFOS, EULER]  # las fuentes no cambian


def test_one_subject_is_not_ambiguous(tmp_path: Path, manifest: Manifest) -> None:
    result = route(
        tmp_path, manifest, [hit(GRAFOS, 0.9), hit(OTRO, 0.85)], "dame la fórmula de Euler"
    )
    assert result.facts == ""


def test_a_clearly_weaker_second_subject_is_not_ambiguous(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path, manifest, [hit(GRAFOS, 0.9), hit(EULER, 0.4)], "dame la fórmula de Euler"
    )
    assert result.facts == ""


def test_the_flag_looks_only_at_the_top_three_notes(tmp_path: Path, manifest: Manifest) -> None:
    notes = [
        hit(GRAFOS, 0.9),
        hit(OTRO, 0.89),
        hit("1º/DISCRETAS/Tema 3 A.md", 0.88),
        hit(EULER, 0.87),
    ]
    assert route(tmp_path, manifest, notes, "euler").facts == ""


def test_existing_facts_are_kept_and_the_note_is_added(tmp_path: Path, manifest: Manifest) -> None:
    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]

    class WithFacts(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, facts="DATO: algo.")

    base = WithFacts([hit(GRAFOS, 0.9), hit(EULER, 0.85)])
    router = IntentRetriever(s, base, NoChunks(), manifest, aliases=ALIASES)
    facts = router.search("euler", k=5).facts
    assert facts.startswith("DATO: algo.") and "AMBIGÜEDAD" in facts


def test_a_question_that_names_a_subject_is_never_flagged(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path,
        manifest,
        [hit(GRAFOS, 0.9), hit(EULER, 0.85)],
        "dame la fórmula de Euler en discreta",
    )
    assert "AMBIGÜEDAD" not in result.facts


def test_a_relevant_note_dropped_by_the_cosine_cutoff_still_counts_as_a_candidate(
    tmp_path: Path, manifest: Manifest
) -> None:
    class Cut(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, candidates=(hit(GRAFOS, 0.88),))

    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    router = IntentRetriever(s, Cut([hit(EULER, 0.9)]), NoChunks(), manifest, aliases=ALIASES)
    result = router.search("dame la fórmula de Euler", k=5)
    assert "AMBIGÜEDAD" in result.facts and "Tema 5 Teoría de grafos" in result.facts
    assert [n.path for n in result.notes] == [EULER]  # solo se responde con las fuentes de siempre


def test_a_weak_candidate_does_not_make_it_ambiguous(tmp_path: Path, manifest: Manifest) -> None:
    class Cut(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, candidates=(hit(GRAFOS, 0.2),))

    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    router = IntentRetriever(s, Cut([hit(EULER, 0.9)]), NoChunks(), manifest, aliases=ALIASES)
    assert router.search("euler", k=5).facts == ""
