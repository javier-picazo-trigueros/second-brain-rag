from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.answer.context import build_context
from secondbrain.answer.pipeline import (
    PARTIAL_NOTE,
    AnswerPipeline,
    DoneEvent,
    SourcesEvent,
    TokenEvent,
)
from secondbrain.answer.prompt import NOT_FOUND, build_messages
from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.exercises import ExerciseBuilder, shorten_tables
from secondbrain.retrieval.families import CopyFamilies
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.intent import detect_intent
from secondbrain.retrieval.overview import IntentRetriever
from secondbrain.retrieval.subjects import SubjectIndex, SubjectSpec
from secondbrain.store.manifest import Manifest
from tests.fakes import FakeRetriever, ScriptedLLM

ALIASES = {
    "Data Mining": SubjectSpec(aliases=("data mining", "dm"), folders=("DM",)),
    "Bases de Datos": SubjectSpec(aliases=("bases de datos", "bd"), folders=("BD",)),
}
PATHS = [
    "3º/DM/DM - Unit 1 - Introduction.md",
    "3º/DM/DM - Unit 2 - Preparation notes.md",
    "3º/DM/DM - Unit 2 - Sample exercises 1.md",
    "3º/DM/DM - Unit 2 - Sample exercises 1 - solution.md",
    "3º/DM/DM - Unit 2 - Sample exercises 2.md",
    "3º/DM/DM - Unit 2 - Sample exercises 2 - solution.md",
    "3º/DM/DM - Unit 3 - Visual notes.md",
    "3º/BD/Ejercicios - Tema 02 - Modelo Relacional.md",
    "3º/BD/Tema 02 - Modelo Relacional.md",
]


@pytest.fixture
def index() -> SubjectIndex:
    return SubjectIndex(PATHS, ALIASES)


# --- intención ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        # las dos frases literales de la prueba real
        "resuélveme el problema/los ejercicios del tema 2 de data mining paso a paso",
        "ve a los ejercicios del tema 2 de data mining y explícame cómo resolverlos",
        # variantes: sin tildes, abreviado, con faltas, otras formas verbales
        "resuelveme los ejercicios del tema 2 de DM",
        "resolver los ejercicios del tema 2 de data mining",
        "haz los ejercicios del unit 2 de data mining",
        "como se resuelven los problemas de la unidad 2 de data mining?",
        "ejercisios del tema 2 de data mining paso a paso",
        "q ejercicios hay del tema 2 de data mining",
        "explicame como resolver el problema 1 del tema 2 de data mining",
        "Quiero practicar con los ejercicios del tema 2 de data mining",
    ],
)
def test_exercise_requests_are_detected_with_subject_and_topic(
    index: SubjectIndex, question: str
) -> None:
    intent = detect_intent(question, index)
    assert intent.kind == "exercises"
    assert intent.subject is not None and intent.subject.name == "Data Mining"
    assert intent.topic == 2


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("explícame el tema 2 de data mining", "overview_topic"),
        ("¿de qué trata el tema 2 de data mining?", "overview_topic"),
        ("¿qué es PCA en data mining?", "search"),
        ("resuelve x + 1 = 2", "search"),  # sin asignatura
        ("ejercicios de PCA", "search"),  # sin asignatura ni tema
        ("¿cómo se resuelve un ejercicio de PCA en data mining?", "search"),  # sin tema
    ],
)
def test_other_questions_keep_their_route(index: SubjectIndex, question: str, kind: str) -> None:
    assert detect_intent(question, index).kind == kind


# --- recuperación -------------------------------------------------------------------------------


class ChunkStore:
    """Chunks reales por nota: `chunks_of` los devuelve en orden de posición."""

    def __init__(self, texts: dict[str, list[str]]) -> None:
        self.texts = texts
        self.asked: list[list[str]] = []

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        self.asked.append(list(paths))
        return [
            {
                "note_path": p,
                "position": i,
                "heading_path": "Ejercicio",
                "page": i + 1,
                "text": text,
                "resumen": None,
            }
            for p in paths
            for i, text in enumerate(self.texts.get(p, ["(vacía)"]))
        ]

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {"note_path": p, "position": 0, "heading_path": "Tema", "resumen": "Resumen."}
            for p in paths
        ]


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


def theory_hit(path: str) -> NoteHit:
    payload = {"note_path": path, "heading_path": "PCA", "page": 4, "text": "Teoría de PCA."}
    return NoteHit(path, path.rsplit("/", 1)[-1][:-3], 0.9, 0.9, (Hit(0.9, payload),), (), 88)


def build(
    tmp_path: Path,
    manifest: Manifest,
    index: SubjectIndex,
    topic: int = 2,
    texts: dict[str, list[str]] | None = None,
    question: str = "",
) -> tuple[SearchResult, ChunkStore, list[list[str]]]:
    store = ChunkStore(texts or {})
    theory_calls: list[list[str]] = []

    def theory(paths: Sequence[str]) -> list[NoteHit]:
        theory_calls.append(list(paths))
        return [theory_hit(p) for p in paths][:2]

    subject = index.by_name("Data Mining")
    assert subject is not None
    result = ExerciseBuilder(settings(tmp_path), store, manifest, CopyFamilies(manifest)).build(
        subject, topic, index.topic_notes(subject, topic), theory, question
    )
    return result, store, theory_calls


def test_only_the_first_exercise_is_solved_with_its_solution_then_the_theory(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index)
    assert result.mode == "exercises"
    assert [n.path for n in result.notes] == [
        "3º/DM/DM - Unit 2 - Sample exercises 1.md",
        "3º/DM/DM - Unit 2 - Sample exercises 1 - solution.md",
        "3º/DM/DM - Unit 2 - Preparation notes.md",
    ]


@pytest.mark.parametrize(
    "question",
    [
        "resuelve el ejercicio 2 del tema 2 de data mining",
        "ve al problema 2 del tema 2 de data mining y explícamelo",
        "sigue con el ejercicio número 2 del tema 2 de data mining",
    ],
)
def test_a_named_exercise_is_the_one_solved(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex, question: str
) -> None:
    result, _, _ = build(tmp_path, manifest, index, question=question)
    assert [n.path for n in result.notes][:2] == [
        "3º/DM/DM - Unit 2 - Sample exercises 2.md",
        "3º/DM/DM - Unit 2 - Sample exercises 2 - solution.md",
    ]
    assert "ejercicio 2 (Sample exercises 2)" in result.facts
    assert "ejercicio 1" in result.facts.split("lista los demás")[1]


def test_an_exercise_number_that_does_not_exist_falls_back_to_the_first(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index, question="resuelve el ejercicio 9 del tema 2")
    assert result.notes[0].path.endswith("Sample exercises 1.md")


def test_the_facts_tell_the_model_to_finish_one_and_offer_the_rest(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index)
    facts = result.facts
    assert "COMPLETO" in facts and "ejercicio 1 (Sample exercises 1)" in facts
    assert "¿Sigo con el ejercicio 2?" in facts
    assert (
        "resuelve el ejercicio 2 del tema 2 de Data Mining" in facts
    )  # cada pregunta es independiente


def test_a_single_exercise_has_no_follow_up_question(tmp_path: Path, index: SubjectIndex) -> None:
    paths = ["3º/DM/DM - Unit 2 - Theory.md", "3º/DM/DM - Unit 2 - Taller PCA.md"]
    m = Manifest(tmp_path / "s1.sqlite")
    for p in paths:
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    idx = SubjectIndex(paths, ALIASES)
    subject = idx.by_name("Data Mining")
    assert subject is not None
    result = ExerciseBuilder(settings(tmp_path), ChunkStore({}), m, CopyFamilies(m)).build(
        subject, 2, idx.topic_notes(subject, 2), lambda ps: []
    )
    m.close()
    assert "¿Sigo con" not in result.facts


def test_it_never_includes_notes_of_another_subject_or_topic(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, store, theory = build(tmp_path, manifest, index)
    everything = {n.path for n in result.notes} | {p for call in store.asked for p in call}
    everything |= {p for call in theory for p in call}
    assert all("/DM/" in p for p in everything)
    assert all("Unit 2" in p for p in everything)


def test_exercise_notes_carry_their_real_chunks_in_order(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    path = "3º/DM/DM - Unit 2 - Sample exercises 1.md"
    result, _, _ = build(tmp_path, manifest, index, texts={path: ["Enunciado A", "Enunciado B"]})
    note = next(n for n in result.notes if n.path == path)
    assert [h.payload["text"] for h in note.chunks] == ["Enunciado A", "Enunciado B"]


def test_the_theory_is_searched_only_among_the_theory_notes_of_the_topic(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    _, _, theory = build(tmp_path, manifest, index)
    assert theory == [["3º/DM/DM - Unit 2 - Preparation notes.md"]]


def test_the_facts_list_every_exercise_and_whether_it_has_a_solution(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index)
    assert "tema 2 de Data Mining" in result.facts
    assert "Sample exercises 1 (con solución)" in result.facts
    assert "Sample exercises 2 (con solución)" in result.facts
    assert result.canned == ""


def test_an_exercise_without_a_solution_is_listed_as_such(
    tmp_path: Path, index: SubjectIndex
) -> None:
    paths = ["3º/DM/DM - Unit 2 - Theory.md", "3º/DM/DM - Unit 2 - Taller PCA.md"]
    m = Manifest(tmp_path / "x.sqlite")
    for p in paths:
        m.upsert(p, "h", 3)
        m.set_meta(p, (), None)
    idx = SubjectIndex(paths, ALIASES)
    subject = idx.by_name("Data Mining")
    assert subject is not None
    builder = ExerciseBuilder(settings(tmp_path), ChunkStore({}), m, CopyFamilies(m))
    result = builder.build(subject, 2, idx.topic_notes(subject, 2), lambda ps: [])
    m.close()
    assert "Taller PCA (sin solución)" in result.facts


def test_a_version_of_an_exercise_collapses_into_one(tmp_path: Path) -> None:
    paths = [
        "3º/DM/DM - Unit 2 - Sample exercises 1.md",
        "3º/DM/DM - Unit 2 - Sample exercises 1 (1).md",
        "3º/DM/DM - Unit 2 - Theory.md",
    ]
    m = Manifest(tmp_path / "v.sqlite")
    for i, p in enumerate(paths):
        m.upsert(p, "h", 3)
        m.set_meta(p, (), f"body{i}")
    idx = SubjectIndex(paths, ALIASES)
    subject = idx.by_name("Data Mining")
    assert subject is not None
    families = CopyFamilies(m, lambda p: "Data Mining")
    result = ExerciseBuilder(settings(tmp_path), ChunkStore({}), m, families).build(
        subject, 2, idx.topic_notes(subject, 2), lambda ps: []
    )
    m.close()
    assert [n.path for n in result.notes].count("3º/DM/DM - Unit 2 - Sample exercises 1.md") == 1
    assert not any("(1)" in n.path for n in result.notes)


# --- sin ejercicios: respuesta determinista, sin modelo ------------------------------------------


def test_a_topic_without_exercises_gets_a_fixed_answer_listing_what_it_has(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, store, _ = build(tmp_path, manifest, index, topic=3)
    assert result.mode == "exercises_none"
    assert result.canned.startswith("No encuentro ejercicios del tema 3 de Data Mining.")
    assert "Del tema 3 tienes:" in result.canned
    assert "- DM - Unit 3 - Visual notes" in result.canned
    assert "apuntes" in result.canned and "teoría" in result.canned
    assert store.asked == []  # ni siquiera se leen chunks


def test_the_fixed_answer_only_lists_notes_of_that_subject_and_topic(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index, topic=3)
    assert "Modelo Relacional" not in result.canned and "Unit 1" not in result.canned


# --- el router ------------------------------------------------------------------------------------


class Base:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Sequence[str] | None]] = []

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult:
        self.calls.append((query, only_paths))
        paths = list(only_paths or [])
        return SearchResult([theory_hit(p) for p in paths][:k], [], 0.8)


def test_the_router_sends_exercise_requests_to_the_exercise_builder(
    tmp_path: Path, manifest: Manifest
) -> None:
    base = Base()
    router = IntentRetriever(
        settings(tmp_path),
        base,
        ChunkStore({}),
        manifest,
        aliases=ALIASES,
        families=CopyFamilies(manifest),
    )
    result = router.search("resuélveme los ejercicios del tema 2 de data mining paso a paso", k=5)
    assert result.mode == "exercises"
    assert all("/DM/" in n.path for n in result.notes)
    # la teoría se busca solo entre las notas de teoría de ese tema
    assert base.calls == [
        (
            "resuélveme los ejercicios del tema 2 de data mining paso a paso",
            ["3º/DM/DM - Unit 2 - Preparation notes.md"],
        )
    ]


def test_the_router_answers_a_missing_topic_with_the_fixed_text(
    tmp_path: Path, manifest: Manifest
) -> None:
    router = IntentRetriever(settings(tmp_path), Base(), ChunkStore({}), manifest, aliases=ALIASES)
    result = router.search("ve a los ejercicios del tema 3 de data mining y explícame", k=5)
    assert result.mode == "exercises_none" and result.canned


def test_a_topic_the_subject_does_not_have_says_so_and_lists_the_topics_it_has(
    tmp_path: Path, manifest: Manifest
) -> None:
    router = IntentRetriever(settings(tmp_path), Base(), ChunkStore({}), manifest, aliases=ALIASES)
    result = router.search("resuelve los ejercicios del tema 9 de data mining", k=5)
    assert result.mode == "exercises_none"
    assert result.canned.startswith("No encuentro ejercicios del tema 9 de Data Mining.")
    assert "no tiene notas del tema 9" in result.canned


# --- contexto, prompt y pipeline ---------------------------------------------------------


def test_the_exercise_context_has_its_own_larger_budget_and_no_hints(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    long = {p: ["palabra " * 400] * 12 for p in PATHS}
    result, _, _ = build(tmp_path, manifest, index, texts=long)
    s = settings(tmp_path)
    context = build_context(result, s)
    assert context.mode == "exercises"
    assert s.context_budget_tokens < context.tokens <= s.exercises_budget_tokens
    assert all(src.kind == "evidence" for src in context.sources)


def test_the_exercise_prompt_asks_for_the_statement_then_the_steps_with_the_theory(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index)
    s = settings(tmp_path)
    system = build_messages("resuelve", build_context(result, s))[0].content
    for phrase in (
        "enunciado", "solución", "paso a paso", "completo", "no recalcules", "cita",
        "más de 6 filas", "no repitas", "solo los pasos",
    ):  # fmt: skip
        assert phrase in system.lower()
    # el worst case sigue cabiendo en la ventana
    messages = build_messages("¿" + "p " * 3000 + "?", build_context(result, s))
    from secondbrain.answer.context import estimate_tokens

    assert (
        sum(estimate_tokens(m.content) for m in messages) + s.exercises_max_tokens <= s.llm_num_ctx
    )


def _pipeline(
    tmp_path: Path, result: SearchResult, deltas: Sequence[str]
) -> tuple[list[Any], ScriptedLLM]:
    llm = ScriptedLLM(deltas)
    pipeline = AnswerPipeline(settings(tmp_path), FakeRetriever(result), llm)
    return list(pipeline.ask("q")), llm


def test_the_pipeline_answers_the_fixed_text_without_calling_the_model(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index, topic=3)
    events, llm = _pipeline(tmp_path, result, ["no debería llamarse"])
    assert llm.calls == 0
    assert isinstance(events[0], SourcesEvent) and events[0].sources  # se pueden abrir las notas
    text = "".join(e.text for e in events if isinstance(e, TokenEvent))
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == text == result.canned
    assert not done.not_found and done.warnings == ()  # ni «sin citas» ni confianza baja


# --- regla: «No lo encuentro» no puede ir tras contenido ----------------------------------------


def found(tmp_path: Path) -> SearchResult:
    return SearchResult([theory_hit("3º/DM/DM - Unit 2 - Preparation notes.md")], [], 0.8)


def test_not_found_after_uncited_content_drops_everything(tmp_path: Path) -> None:
    deltas = ["Para resolverlo, calcula la media. ", "Luego resta. ", NOT_FOUND, " Más texto."]
    events, _ = _pipeline(tmp_path, found(tmp_path), deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == NOT_FOUND and done.not_found
    assert "respuesta_contradictoria" in done.warnings
    assert "respuesta_parcial" not in done.warnings
    streamed = "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert "Más texto" not in streamed  # se cortó la generación al verla


def test_not_found_after_content_keeps_only_the_sentences_with_verified_citations(
    tmp_path: Path,
) -> None:
    deltas = [
        "Dato cierto [S1]. Invento sin cita. Otro cierto [S1]. ",
        "Cita falsa [S9]. ",
        NOT_FOUND,
        " Más texto.",
    ]
    events, _ = _pipeline(tmp_path, found(tmp_path), deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == f"Dato cierto [S1]. Otro cierto [S1].\n\n{PARTIAL_NOTE}"
    assert "respuesta_parcial" in done.warnings
    assert "respuesta_contradictoria" not in done.warnings
    assert not done.not_found
    assert [c.id for c in done.citations] == ["S1"] and done.invalid == ()


def test_the_partial_answer_keeps_whole_list_lines_with_citations(tmp_path: Path) -> None:
    deltas = ["- Con cita [S1]\n- Inventado sin cita\n- Otra con cita [S1]\n", NOT_FOUND]
    events, _ = _pipeline(tmp_path, found(tmp_path), deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == f"- Con cita [S1]\n- Otra con cita [S1]\n\n{PARTIAL_NOTE}"


def test_not_found_at_the_start_is_a_normal_answer_with_its_suggestion(tmp_path: Path) -> None:
    deltas = [NOT_FOUND, "\n\nPodrías mirar: [S1]"]
    events, _ = _pipeline(tmp_path, found(tmp_path), deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer.startswith(NOT_FOUND) and "Podrías mirar" in done.answer
    assert done.not_found and "respuesta_contradictoria" not in done.warnings


def test_not_found_split_across_deltas_is_still_caught(tmp_path: Path) -> None:
    deltas = ["Resultado: 42. ", "No lo encuentro ", "en el vault."]
    events, _ = _pipeline(tmp_path, found(tmp_path), deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == NOT_FOUND and "respuesta_contradictoria" in done.warnings


def test_an_ordinary_answer_is_untouched(tmp_path: Path) -> None:
    events, _ = _pipeline(tmp_path, found(tmp_path), ["Un dato [S1]."])
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == "Un dato [S1]." and "respuesta_contradictoria" not in done.warnings


def test_exercise_answers_get_a_larger_output_limit_than_ordinary_ones(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index)
    _, llm = _pipeline(tmp_path, result, ["Paso 1 [S1]."])
    assert llm.max_tokens == settings(tmp_path).exercises_max_tokens
    assert llm.max_tokens is not None and llm.max_tokens > settings(tmp_path).llm_max_tokens
    _, ordinary = _pipeline(tmp_path, found(tmp_path), ["Un dato [S1]."])
    assert ordinary.max_tokens is None


def test_the_budget_leaves_room_for_the_long_answer_even_with_numeric_text(
    tmp_path: Path,
) -> None:
    """El estimador de tokens infravalora el texto numérico (~1,5x): el margen lo absorbe."""
    s = settings(tmp_path)
    assert s.exercises_budget_tokens * 1.6 + s.exercises_max_tokens + 1200 <= s.llm_num_ctx


# --- números y pasos: lo que no sale de la fuente se avisa ------------------------------

SOLUTION_TEXTS = {
    "3º/DM/DM - Unit 2 - Sample exercises 1.md": ["Enunciado: 301 pizzas, 7 variables."],
    "3º/DM/DM - Unit 2 - Sample exercises 1 - solution.md": [
        "Eigenvalues: 0.76384, 0.0202. Variance %: 0.951043, 0.025151. Suma 0.80316."
    ],
}


def exercise_run(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex, deltas: Sequence[str]
) -> DoneEvent:
    result, _, _ = build(tmp_path, manifest, index, texts=SOLUTION_TEXTS)
    events, _ = _pipeline(tmp_path, result, deltas)
    done = events[-1]
    assert isinstance(done, DoneEvent)
    return done


def test_a_number_that_is_not_in_the_sources_is_reported(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    done = exercise_run(
        tmp_path, manifest, index, ["Paso 1: la suma de autovalores es 0,79209 [S2]."]
    )
    assert "numeros_no_verificados" in done.warnings
    assert done.unverified_numbers == ("0,79209",)


def test_numbers_copied_from_the_solution_are_never_reported(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    deltas = [
        "Paso 1: autovalores 0.76384 y 0,0202 [S2].\n",
        "Paso 2: varianza 0.951043 [S2], es decir 95,1043 % del total [S2].\n",
        "Paso 3: 301 pizzas con 7 variables y suma 0.80316 [S1][S2].",
    ]
    done = exercise_run(tmp_path, manifest, index, deltas)
    assert done.unverified_numbers == () and "numeros_no_verificados" not in done.warnings


def test_small_counts_and_step_numbers_are_not_numbers_to_verify(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    done = exercise_run(
        tmp_path, manifest, index, ["Paso 1: hay 2 ejercicios y 3 pasos [S2].\nPaso 2: ver [S2]."]
    )
    assert done.unverified_numbers == ()


def test_the_number_check_only_applies_to_exercise_answers(tmp_path: Path) -> None:
    events, _ = _pipeline(tmp_path, found(tmp_path), ["Vale 12345,678 [S1]."])
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.unverified_numbers == () and "numeros_no_verificados" not in done.warnings


def test_steps_without_a_citation_are_counted_and_flagged(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    deltas = [
        "Paso 1: leer el enunciado [S1].\nPaso 2: calcular sin fuente.\n- detalle del paso 2\n"
        "Paso 3: otro sin cita.\nPaso 4: resultado [S2]"
    ]
    done = exercise_run(tmp_path, manifest, index, deltas)
    assert done.uncited_steps == 2 and "pasos_sin_cita" in done.warnings


def test_an_exercise_answer_with_a_citation_in_every_step_raises_no_step_warning(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    deltas = ["Paso 1: leer [S1].\nPaso 2: copiar el resultado [S2].\n- Conclusión [S2]"]
    done = exercise_run(tmp_path, manifest, index, deltas)
    assert done.uncited_steps == 0 and "pasos_sin_cita" not in done.warnings


def test_an_exercise_answer_without_any_citation_is_flagged_as_uncited(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    done = exercise_run(tmp_path, manifest, index, ["Paso 1: algo.\nPaso 2: otra cosa."])
    assert "sin_citas" in done.warnings and done.uncited_steps == 2


def test_every_fragment_of_the_exercise_context_is_citable_with_its_own_id(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    result, _, _ = build(tmp_path, manifest, index, texts=SOLUTION_TEXTS)
    context = build_context(result, settings(tmp_path))
    ids = [f.id for f in context.fragments]
    assert ids == [f"S{i}" for i in range(1, len(ids) + 1)]
    for fragment_id in ids:
        assert f"[{fragment_id}]" in context.text  # cabecera «### [S#]» de cada fragmento


# --- tablas enormes: el modelo no puede copiarlas enteras --------------------------------


def table(rows: int) -> str:
    lines = ["|PC|valor|", "|---|---|"] + [f"|{i}|0.{i:03d}|" for i in range(1, rows + 1)]
    return "\n".join(lines)


def test_a_long_table_keeps_its_header_and_the_first_rows_and_says_how_many_are_left() -> None:
    out = shorten_tables(f"Antes\n\n{table(13)}\n\nDespués", keep=8)
    assert out.count("\n|") == 9 + 1 - 1  # cabecera + separador + 8 filas, contadas por saltos
    assert "|8|0.008|" in out and "|9|0.009|" not in out
    assert "5 filas más de esta tabla en la fuente" in out
    assert out.startswith("Antes") and out.endswith("Después")


def test_a_short_table_and_plain_text_are_untouched() -> None:
    text = f"Un texto con | barra\n\n{table(8)}\n\nFin"
    assert shorten_tables(text, keep=8) == text
    assert shorten_tables("sin tablas", keep=8) == "sin tablas"


def test_two_long_tables_are_each_shortened() -> None:
    out = shorten_tables(f"{table(12)}\n\ntexto\n\n{table(20)}", keep=8)
    assert "4 filas más" in out and "12 filas más" in out


def test_the_exercise_chunks_given_to_the_model_have_their_tables_shortened(
    tmp_path: Path, manifest: Manifest, index: SubjectIndex
) -> None:
    solution = "3º/DM/DM - Unit 2 - Sample exercises 1 - solution.md"
    result, _, _ = build(tmp_path, manifest, index, texts={solution: [table(30)]})
    note = next(n for n in result.notes if n.path == solution)
    text = str(note.chunks[0].payload["text"])
    assert "22 filas más de esta tabla en la fuente" in text and "|30|" not in text
