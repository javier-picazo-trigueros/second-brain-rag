from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.answer.pipeline import (
    AnswerPipeline,
    DoneEvent,
    ProgressEvent,
    SourcesEvent,
    TokenEvent,
)
from secondbrain.answer.prompt import NOT_FOUND, build_study_messages
from secondbrain.config import Settings
from secondbrain.retrieval.families import CopyFamilies
from secondbrain.retrieval.hybrid import SearchResult
from secondbrain.retrieval.intent import detect_intent
from secondbrain.retrieval.overview import IntentRetriever
from secondbrain.retrieval.study import StudyPlanner
from secondbrain.retrieval.subjects import SubjectIndex, SubjectSpec
from secondbrain.store.manifest import Manifest
from tests.fakes import FakeRetriever, ScriptedLLM

ALIASES = {
    "Matemática Discreta": SubjectSpec(
        aliases=("discreta", "matematica discreta", "md"), folders=("Discreta",)
    ),
    "Sistemas Operativos": SubjectSpec(
        aliases=("sistemas operativos", "so", "ssoo"), folders=("SO",)
    ),
}
T5 = "3º/Discreta/Tema 5 Teoría de grafos.md"
R5 = "3º/Discreta/Resumen Tema 5.md"
E5 = "3º/Discreta/Tema 5_Ejercicios.md"
E5S = "3º/Discreta/Tema 5_Ejercicios_Soluciones.md"
T4 = "3º/Discreta/Tema 4 Números.md"
SO3A = "2º/SO/Tema-3.1 Procesos e Hilos.md"
SO3B = "2º/SO/Tema-3.2 Gestión de Hilos.md"
PATHS = [T5, R5, E5, E5S, T4, SO3A, SO3B]


@pytest.fixture
def index() -> SubjectIndex:
    return SubjectIndex(PATHS, ALIASES)


# --- intención ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "genérame unos apuntes del tema 5 de discreta",
        "hazme apuntes del tema 5 de matematica discreta",
        "hazme unos apuntes de la unidad 5 de discreta",
        "generame apuntes del tema 5 de MD",
        "explícame en detalle el tema 5 de discreta",
        "explicame a fondo el tema 5 de discreta",
        "explícame con detalle el tema 5 de discreta",
        "quiero unos apuntes completos del tema 5 de discreta",
        "aputnes del tema 5 de discreta",
    ],
)
def test_apuntes_requests_are_detected(index: SubjectIndex, question: str) -> None:
    intent = detect_intent(question, index)
    assert intent.kind == "notes", question
    assert intent.subject is not None and intent.subject.name == "Matemática Discreta"
    assert intent.topic == 5


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("explícame el tema 5 de discreta", "overview_topic"),
        ("de qué va el tema 5 de discreta", "overview_topic"),
        ("hazme apuntes de discreta", "search"),  # sin tema: esta versión no los hace
        ("resuélveme los ejercicios del tema 5 de discreta", "exercises"),
        ("explícame en detalle qué es un grafo", "search"),  # sin asignatura ni tema
    ],
)
def test_neighbouring_requests_keep_their_route(
    index: SubjectIndex, question: str, kind: str
) -> None:
    assert detect_intent(question, index).kind == kind


# --- plan --------------------------------------------------------------------------------


class ChunkStore:
    def __init__(self, notes: dict[str, list[str]]) -> None:
        self.notes = notes
        self.asked: list[list[str]] = []

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        self.asked.append(list(paths))
        return [
            {
                "note_path": p,
                "position": i,
                "heading_path": f"Apartado {i // 2 + 1}",
                "page": i + 1,
                "text": text,
                "resumen": None,
            }
            for p in paths
            for i, text in enumerate(self.notes.get(p, []))
        ]

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "m.sqlite")
    for p in PATHS:
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    yield m
    m.close()


def settings(tmp_path: Path, **over: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **over)  # type: ignore[call-arg]


BIG = {
    T5: [f"Texto {i} " + "palabra " * 400 for i in range(10)],  # ~800 tokens estimados cada uno
    R5: ["Resumen del tema: grafos, caminos y árboles."],
    E5: ["Ejercicio 1: halla el camino mínimo.", "Ejercicio 2: colorea el grafo."],
    E5S: ["Solución 1: usa Dijkstra."],
    T4: ["Otro tema."],
}


def plan_for(tmp_path: Path, manifest: Manifest, index: SubjectIndex, **over: Any) -> Any:
    store = ChunkStore(BIG)
    subject = index.by_name("Matemática Discreta")
    assert subject is not None
    planner = StudyPlanner(settings(tmp_path, **over), store, manifest, CopyFamilies(manifest))
    return planner.plan(subject, 5, index.topic_notes(subject, 5)), store


def test_the_plan_walks_the_real_fragments_in_page_order_split_in_windows(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index, notes_window_tokens=2000)
    theory = [p for p in plan.parts if p.kind == "theory"]
    assert len(theory) >= 3
    ids = [f.id for p in plan.parts for f in p.fragments]
    assert ids == [f"S{i}" for i in range(1, len(ids) + 1)]  # numeración global
    pages = [f.page for p in theory for f in p.fragments if f.path == T5]
    assert pages == sorted(pages) and pages[0] == 1  # orden de página, desde el principio
    assert all(len(p.fragments) > 0 for p in plan.parts)


def test_each_window_fits_in_its_token_budget(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index, notes_window_tokens=2000)
    for part in (p for p in plan.parts if p.kind == "theory"):
        tokens = sum(len(f.text) // 4 for f in part.fragments)
        assert tokens <= 2000 + 900  # un chunk de margen como mucho


def test_only_theory_of_the_topic_feeds_the_theory_parts(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, store = plan_for(tmp_path, manifest, index)
    theory_paths = {f.path for p in plan.parts if p.kind == "theory" for f in p.fragments}
    assert theory_paths <= {T5, R5}  # nada de ejercicios, ni de otro tema, ni de otra asignatura
    assert plan.subject == "Matemática Discreta" and plan.topic == 5
    assert all("Tema 4" not in p and "SO" not in p for call in store.asked for p in call)


def test_the_summary_is_the_skeleton_not_a_part_of_its_own(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index)
    assert "grafos, caminos y árboles" in plan.skeleton
    assert R5 not in {f.path for p in plan.parts if p.kind == "theory" for f in p.fragments}


def test_exercise_notes_only_feed_the_last_part(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index)
    last = plan.parts[-1]
    assert last.kind == "exercises"
    assert {f.path for f in last.fragments} == {E5, E5S}
    assert [p.kind for p in plan.parts[:-1]] == ["theory"] * (len(plan.parts) - 1)


def test_a_topic_without_exercises_has_no_exercise_part(
    tmp_path: Path, index: SubjectIndex
) -> None:
    paths = [T5, R5]
    m = Manifest(tmp_path / "x.sqlite")
    for p in paths:
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    idx = SubjectIndex(paths, ALIASES)
    subject = idx.by_name("Matemática Discreta")
    assert subject is not None
    plan = StudyPlanner(settings(tmp_path), ChunkStore(BIG), m, CopyFamilies(m)).plan(
        subject, 5, idx.topic_notes(subject, 5)
    )
    m.close()
    assert plan is not None and all(p.kind == "theory" for p in plan.parts)


def test_no_theory_means_no_plan(tmp_path: Path, manifest: Manifest, index: SubjectIndex) -> None:
    subject = index.by_name("Matemática Discreta")
    assert subject is not None
    planner = StudyPlanner(settings(tmp_path), ChunkStore(BIG), manifest, CopyFamilies(manifest))
    assert planner.plan(subject, 5, [E5, E5S]) is None


def test_the_router_returns_the_plan_for_apuntes_and_not_a_search(
    tmp_path: Path, manifest: Manifest
) -> None:
    class Base:
        calls = 0

        def search(self, *a: Any, **k: Any) -> SearchResult:
            Base.calls += 1
            return SearchResult([], [], 0.5)

    router = IntentRetriever(
        settings(tmp_path), Base(), ChunkStore(BIG), manifest, aliases=ALIASES,
        families=CopyFamilies(manifest),
    )  # fmt: skip
    result = router.search("genérame unos apuntes del tema 5 de discreta", k=5)
    assert result.mode == "notes" and result.study is not None and Base.calls == 0


class NoSearch:
    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult:
        raise AssertionError("no debería buscarse")


def test_apuntes_of_a_missing_topic_say_so_without_the_model(
    tmp_path: Path, manifest: Manifest
) -> None:
    router = IntentRetriever(
        settings(tmp_path), NoSearch(), ChunkStore(BIG), manifest, aliases=ALIASES
    )
    result = router.search("hazme apuntes del tema 9 de discreta", k=5)
    assert result.study is None and result.canned.startswith("No encuentro apuntes del tema 9")


# --- escritura por partes ----------------------------------------------------------------


def run(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex, deltas: Sequence[str], **over: Any
) -> tuple[list[Any], ScriptedLLM]:
    plan, _ = plan_for(tmp_path, manifest, index, **over)
    llm = ScriptedLLM(deltas)
    pipeline = AnswerPipeline(
        settings(tmp_path, **over),
        FakeRetriever(SearchResult([], [], None, mode="notes", study=plan)),
        llm,
    )
    return list(pipeline.ask("apuntes")), llm


def test_the_writer_makes_one_model_call_per_part_with_progress_events(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    events, llm = run(tmp_path, manifest, index, ["### Parte [S1]."], notes_window_tokens=2000)
    progress = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(progress) == llm.calls >= 4
    assert [p.part for p in progress] == list(range(1, len(progress) + 1))
    assert all(p.total == len(progress) for p in progress)
    assert progress[-1].title.lower().startswith("tipos de ejercicio")
    assert isinstance(events[0], SourcesEvent) and isinstance(events[-1], DoneEvent)


def test_the_parts_are_joined_in_order_under_a_title(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    events, _ = run(tmp_path, manifest, index, ["Sección [S1]."], notes_window_tokens=2000)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer.startswith("# Apuntes del tema 5 de Matemática Discreta")
    assert done.answer.count("Sección") == sum(isinstance(e, ProgressEvent) for e in events)
    streamed = "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert streamed == done.answer  # lo que se ve es lo que se guarda


def test_each_part_sees_only_its_own_fragments_and_the_skeleton(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    _, llm = run(tmp_path, manifest, index, ["x"], notes_window_tokens=2000)
    user = llm.messages[-1].content
    assert "Tipos de ejercicio" in user or "EJERCICIOS" in user
    assert "Texto 0 " not in user  # los fragmentos de las partes anteriores no se repiten


def test_the_prompt_demands_detail_latex_and_forbids_inventing(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index)
    first = build_study_messages(plan, plan.parts[0], 1, len(plan.parts))
    system = first[0].content.lower()
    for phrase in ("definiciones", "teoremas", "enunciado", "ejemplos", "latex", "no inventes"):
        assert phrase in system
    assert "grafos, caminos y árboles" in first[1].content  # el esqueleto acompaña a cada parte


def test_every_part_gets_the_larger_output_limit(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    _, llm = run(tmp_path, manifest, index, ["x"])
    assert llm.max_tokens == settings(tmp_path).notes_part_max_tokens


def test_a_part_that_says_not_found_after_content_is_dropped_and_flagged(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    events, _ = run(
        tmp_path, manifest, index, ["Invento cosas. ", NOT_FOUND], notes_window_tokens=2000
    )
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert "Invento" not in done.answer and NOT_FOUND not in done.answer
    assert "respuesta_contradictoria" in done.warnings


def test_citations_are_collected_across_parts(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    events, _ = run(tmp_path, manifest, index, ["Dato [S1]. Otro [S2]."])
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert {c.id for c in done.citations} >= {"S1", "S2"}
    assert done.invalid == ()


def test_the_done_event_says_it_is_study_notes_with_subject_and_topic(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    events, _ = run(tmp_path, manifest, index, ["x [S1]"])
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert (done.mode, done.subject, done.topic) == ("notes", "Matemática Discreta", 5)


def test_a_failing_model_ends_with_an_error_event_keeping_what_was_streamed(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index, notes_window_tokens=2000)
    llm = ScriptedLLM(["Parte [S1]."], fail_after=1)
    pipeline = AnswerPipeline(
        settings(tmp_path), FakeRetriever(SearchResult([], [], None, mode="notes", study=plan)), llm
    )
    events = list(pipeline.ask("apuntes"))
    assert type(events[-1]).__name__ == "ErrorEvent"


def test_notes_follow_the_syllabus_order_of_their_sections_not_their_folder(
    tmp_path: Path,
) -> None:
    paths = ["3º/SO/Tema-3.2 B.md", "2º/SO/Tema-3.3 C.md", "2º/SO/Tema-3.1 A.md"]
    m = Manifest(tmp_path / "o.sqlite")
    for p in paths:
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    idx = SubjectIndex(
        paths, {"Sistemas Operativos": SubjectSpec(aliases=("so",), folders=("SO",))}
    )
    subject = idx.by_name("Sistemas Operativos")
    assert subject is not None
    store = ChunkStore({p: ["texto " + p] for p in paths})
    plan = StudyPlanner(settings(tmp_path), store, m, CopyFamilies(m)).plan(
        subject, 3, idx.topic_notes(subject, 3)
    )
    m.close()
    assert plan is not None
    order = [f.path for part in plan.parts for f in part.fragments]
    assert order == ["2º/SO/Tema-3.1 A.md", "3º/SO/Tema-3.2 B.md", "2º/SO/Tema-3.3 C.md"]


def test_part_titles_say_which_note_and_pages_never_markdown_noise(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    plan, _ = plan_for(tmp_path, manifest, index, notes_window_tokens=2000)
    theory = [p for p in plan.parts if p.kind == "theory"]
    assert theory[0].title == "Teoría de grafos · págs. 1"
    assert all("*" not in p.title and "#" not in p.title for p in plan.parts)
    assert [p.title.split(" · ")[1].split()[0] for p in theory] == ["págs."] * len(theory)
