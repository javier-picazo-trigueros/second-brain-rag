from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from secondbrain.answer.llm import Delta, Finished, LLMError, Message
from secondbrain.answer.pipeline import (
    AnswerPipeline,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    confidence_label,
)
from secondbrain.answer.prompt import NOT_FOUND
from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import NoteHit, RelatedNote, SearchResult


def settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]


def chunk(path: str, text: str, page: int | None = None) -> Hit:
    payload = {
        "note_path": path,
        "heading_path": "Tema",
        "page": page,
        "text": text,
        "asignatura": "SISTEMAS",
        "curso": "2º",
    }
    return Hit(0.5, payload)


def note(path: str, text: str = "Un semáforo es un contador.", page: int | None = 7) -> NoteHit:
    title = path.rsplit("/", 1)[-1][:-3]
    return NoteHit(path, title, 0.5, 0.5, (chunk(path, text, page),), (), 4)


def found(similarity: float | None = 0.8, hints: list[RelatedNote] | None = None) -> SearchResult:
    return SearchResult([note("1º/SO/Semáforos.md")], hints or [], similarity)


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


def run(
    tmp_path: Path,
    result: SearchResult,
    deltas: Sequence[str],
    *,
    finished: Finished | None = FINISHED,
    fail_after: int | None = None,
    k: int | None = None,
    **overrides: Any,
) -> tuple[list[Any], FakeRetriever, ScriptedLLM]:
    retriever = FakeRetriever(result)
    llm = ScriptedLLM(deltas, finished, fail_after)
    pipeline = AnswerPipeline(settings(tmp_path, **overrides), retriever, llm, clock=Tick())
    return list(pipeline.ask("¿Qué es un semáforo?", k=k)), retriever, llm


def done(events: list[Any]) -> DoneEvent:
    assert isinstance(events[-1], DoneEvent), events[-1]
    return events[-1]


def text_of(events: list[Any]) -> str:
    return "".join(e.text for e in events if isinstance(e, TokenEvent))


# --- orden y contenido de los eventos -------------------------------------------------------------


def test_events_arrive_in_order_sources_tokens_done(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Un semáforo cuenta ", "[[Semáforos]] (p. 7)."])
    assert isinstance(events[0], SourcesEvent)
    assert all(isinstance(e, TokenEvent) for e in events[1:-1])
    assert isinstance(events[-1], DoneEvent)


def test_the_streamed_text_equals_the_final_answer(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Un semáforo cuenta ", "[[Semáforos]] (p. 7)."])
    assert text_of(events) == done(events).answer == "Un semáforo cuenta [[Semáforos]] (p. 7)."


def test_sources_event_lists_the_notes_the_model_can_cite(tmp_path: Path) -> None:
    hint = RelatedNote("2º/Redes.md", 1.0, ("c",), ("a",), "Resumen.", "H", None, None)
    events, _, _ = run(tmp_path, found(hints=[hint]), ["Respuesta [[Semáforos]]."])
    sources = events[0].sources
    assert [(s.label, s.kind) for s in sources] == [("Semáforos", "evidence"), ("Redes", "hint")]
    assert sources[0].pages == (7,)


def test_the_prompt_sent_to_the_model_contains_the_context_and_the_question(tmp_path: Path) -> None:
    _, _, llm = run(tmp_path, found(), ["ok [[Semáforos]]"])
    assert [m.role for m in llm.messages] == ["system", "user"]
    assert "Un semáforo es un contador." in llm.messages[1].content
    assert "¿Qué es un semáforo?" in llm.messages[1].content


def test_k_is_passed_to_the_retriever_and_defaults_to_the_setting(tmp_path: Path) -> None:
    _, retriever, _ = run(tmp_path, found(), ["x [[Semáforos]]"], k=3)
    assert retriever.calls == [("¿Qué es un semáforo?", 3)]
    _, retriever, _ = run(tmp_path, found(), ["x [[Semáforos]]"], answer_k=7)
    assert retriever.calls[0][1] == 7


# --- citas -----------------------------------------------------------------------------------


def test_unverified_citations_are_marked_in_the_stream_and_reported(tmp_path: Path) -> None:
    deltas = ["Dato [[Inve", "ntada]] y [[Semáforos]] (p. 7)."]
    events, _, _ = run(tmp_path, found(), deltas)
    d = done(events)
    assert "[[Inventada" not in text_of(events)
    assert "[cita no verificada: Inventada]" in d.answer
    assert d.invalid == ("Inventada",)
    assert [(c.path, c.page) for c in d.citations] == [("1º/SO/Semáforos.md", 7)]
    assert "citas_no_verificadas" in d.warnings


def test_a_page_not_in_the_context_is_flagged(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Cuenta [[Semáforos]] (p. 99)."])
    d = done(events)
    assert "(p. 99 no verificada)" in d.answer
    assert "paginas_no_verificadas" in d.warnings


# --- avisos -------------------------------------------------------------------------------------


def test_an_answer_without_citations_is_flagged(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Un semáforo es un contador."])
    assert "sin_citas" in done(events).warnings


def test_citing_only_related_hints_is_flagged(tmp_path: Path) -> None:
    hint = RelatedNote("2º/Redes.md", 1.0, ("c",), ("a",), "Resumen.", "H", None, None)
    events, _, _ = run(tmp_path, found(hints=[hint]), ["Ver también [[Redes]]."])
    assert "solo_pistas" in done(events).warnings


def test_a_clean_cited_answer_has_no_warnings(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Es un contador [[Semáforos]] (p. 7)."])
    d = done(events)
    assert d.warnings == () and d.not_found is False


def test_a_truncated_generation_is_flagged(tmp_path: Path) -> None:
    cut = Finished(900, 1024, 0.0, 400.0, 20000.0, truncated=True)
    events, _, _ = run(tmp_path, found(), ["Es [[Semáforos]]"], finished=cut)
    assert "respuesta_truncada" in done(events).warnings


def test_a_trimmed_context_is_flagged(tmp_path: Path) -> None:
    big = [note(f"c/N{i}.md", "palabra " * 600) for i in range(6)]
    events, _, _ = run(
        tmp_path, SearchResult(big, [], 0.8), ["x [[N0]]"], context_budget_tokens=1500,
        related_budget_tokens=0,
    )  # fmt: skip
    assert "contexto_recortado" in done(events).warnings


# --- sin contexto / el modelo no sabe -------------------------------------------


def test_with_no_retrieved_notes_the_model_is_not_called(tmp_path: Path) -> None:
    events, _, llm = run(tmp_path, SearchResult([], [], None), ["no debería usarse"])
    d = done(events)
    assert llm.calls == 0
    assert d.answer == NOT_FOUND and d.not_found is True
    assert text_of(events) == NOT_FOUND


def test_when_the_model_says_it_is_not_in_the_vault_that_is_not_a_warning(tmp_path: Path) -> None:
    events, _, _ = run(
        tmp_path, found(similarity=0.9), [f"{NOT_FOUND} Podrías mirar [[Semáforos]]."]
    )
    d = done(events)
    assert d.not_found is True
    assert "sin_citas" not in d.warnings


# --- confianza ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("similarity", "expected"),
    [(0.8, "alta"), (0.5, "alta"), (0.49, "baja"), (None, "desconocida")],
)
def test_confidence_label(similarity: float | None, expected: str) -> None:
    assert confidence_label(similarity, 0.5) == expected


def test_low_similarity_is_reported_but_does_not_block_the_answer(tmp_path: Path) -> None:
    events, _, llm = run(tmp_path, found(similarity=0.3), ["Es [[Semáforos]]"])
    d = done(events)
    assert (d.confidence, d.similarity) == ("baja", 0.3)
    assert "confianza_baja" in d.warnings
    assert llm.calls == 1
    assert events[0].confidence == "baja"


def test_the_threshold_comes_from_the_settings(tmp_path: Path) -> None:
    events, _, _ = run(
        tmp_path, found(similarity=0.3), ["Es [[Semáforos]]"], confidence_threshold=0.2
    )
    assert done(events).confidence == "alta"


# --- errores y medidas -------------------------------------------------------------


def test_a_model_failure_before_any_token_becomes_an_error_event(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["x"], fail_after=0)
    assert isinstance(events[-1], ErrorEvent)
    assert "ollama serve" in events[-1].message
    assert not any(isinstance(e, DoneEvent) for e in events)


def test_a_model_failure_mid_answer_keeps_what_was_already_sent(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Un semáforo ", "es ", "algo"], fail_after=2)
    assert text_of(events) == "Un semáforo es "
    assert isinstance(events[-1], ErrorEvent)


def test_timings_and_token_counts(tmp_path: Path) -> None:
    events, _, _ = run(tmp_path, found(), ["Es ", "[[Semáforos]]."])
    d = done(events)
    assert d.timings.retrieval_ms > 0
    assert d.timings.first_token_ms is not None
    assert d.timings.retrieval_ms <= d.timings.first_token_ms <= d.timings.total_ms
    assert (d.prompt_tokens, d.completion_tokens) == (900, 50)
    assert d.timings.tokens_per_second == pytest.approx(50.0)


def test_the_first_token_time_is_measured_when_text_reaches_the_client(tmp_path: Path) -> None:
    # Si el modelo empieza con una cita, el primer texto visible sale cuando se valida la cita.
    events, _, _ = run(tmp_path, found(), ["[[Sem", "áforos]] ", "es un contador."])
    assert done(events).timings.first_token_ms is not None
