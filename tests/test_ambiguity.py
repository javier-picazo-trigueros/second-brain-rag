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
    assert result.ambiguity and result.facts == ""
    assert "Matemática Discreta" in result.ambiguity and "Cálculo" in result.ambiguity
    assert "Tema 5 Teoría de grafos" in result.ambiguity and "Método de Euler" in result.ambiguity
    assert result.ambiguity.startswith("Ojo:") and "concreta la pregunta" in result.ambiguity
    assert [n.path for n in result.notes] == [GRAFOS, EULER]  # las fuentes no cambian


def test_one_subject_is_not_ambiguous(tmp_path: Path, manifest: Manifest) -> None:
    result = route(
        tmp_path, manifest, [hit(GRAFOS, 0.9), hit(OTRO, 0.85)], "dame la fórmula de Euler"
    )
    assert result.ambiguity == ""


def test_a_clearly_weaker_second_subject_is_not_ambiguous(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path, manifest, [hit(GRAFOS, 0.9), hit(EULER, 0.4)], "dame la fórmula de Euler"
    )
    assert result.ambiguity == ""


def test_the_flag_looks_only_at_the_top_three_notes(tmp_path: Path, manifest: Manifest) -> None:
    notes = [
        hit(GRAFOS, 0.9),
        hit(OTRO, 0.89),
        hit("1º/DISCRETAS/Tema 3 A.md", 0.88),
        hit(EULER, 0.87),
    ]
    assert route(tmp_path, manifest, notes, "euler").ambiguity == ""


def test_existing_facts_are_left_untouched(tmp_path: Path, manifest: Manifest) -> None:
    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]

    class WithFacts(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, facts="DATO: algo.")

    base = WithFacts([hit(GRAFOS, 0.9), hit(EULER, 0.85)])
    router = IntentRetriever(s, base, NoChunks(), manifest, aliases=ALIASES)
    result = router.search("euler", k=5)
    assert result.facts == "DATO: algo." and result.ambiguity


def test_the_warning_names_the_subject_the_answer_will_use(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path, manifest, [hit(EULER, 0.9), hit(GRAFOS, 0.85)], "dame la fórmula de Euler"
    )
    assert "Respondo con las fuentes de «Cálculo»" in result.ambiguity


def test_a_question_that_names_a_subject_is_never_flagged(
    tmp_path: Path, manifest: Manifest
) -> None:
    result = route(
        tmp_path,
        manifest,
        [hit(GRAFOS, 0.9), hit(EULER, 0.85)],
        "dame la fórmula de Euler en discreta",
    )
    assert result.ambiguity == ""


def test_a_relevant_note_dropped_by_the_cosine_cutoff_still_counts_as_a_candidate(
    tmp_path: Path, manifest: Manifest
) -> None:
    class Cut(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, candidates=(hit(GRAFOS, 0.88),))

    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    router = IntentRetriever(s, Cut([hit(EULER, 0.9)]), NoChunks(), manifest, aliases=ALIASES)
    result = router.search("dame la fórmula de Euler", k=5)
    assert "Tema 5 Teoría de grafos" in result.ambiguity and result.facts == ""
    assert [n.path for n in result.notes] == [EULER]  # solo se responde con las fuentes de siempre


def test_a_weak_candidate_does_not_make_it_ambiguous(tmp_path: Path, manifest: Manifest) -> None:
    class Cut(Base):
        def search(self, *a: Any, **k: Any) -> SearchResult:
            return SearchResult(self.notes, [], 0.8, candidates=(hit(GRAFOS, 0.2),))

    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    router = IntentRetriever(s, Cut([hit(EULER, 0.9)]), NoChunks(), manifest, aliases=ALIASES)
    assert router.search("euler", k=5).ambiguity == ""


# --- el pipeline antepone la frase, sin depender del modelo ---------------


def test_the_pipeline_puts_the_ambiguity_sentence_first_and_keeps_the_model_answer(
    tmp_path: Path,
) -> None:
    from secondbrain.answer.pipeline import AnswerPipeline, DoneEvent, TokenEvent
    from tests.fakes import FakeRetriever, ScriptedLLM

    result = SearchResult(
        [hit(EULER, 0.9)], [], 0.8, ambiguity="Ojo: puede ser de dos asignaturas."
    )
    llm = ScriptedLLM(["La fórmula es y' = f [S1]."])
    s: Any = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    events = list(AnswerPipeline(s, FakeRetriever(result), llm).ask("euler"))
    streamed = "".join(e.text for e in events if isinstance(e, TokenEvent))
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert streamed.startswith("Ojo: puede ser de dos asignaturas.\n\n")
    assert done.answer == "Ojo: puede ser de dos asignaturas.\n\nLa fórmula es y' = f [S1]."
    assert [c.id for c in done.citations] == ["S1"]
    assert "Ojo" not in llm.messages[1].content  # el modelo no ve la frase: es del sistema
