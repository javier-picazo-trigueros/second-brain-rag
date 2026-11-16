from __future__ import annotations

from pathlib import Path
from typing import Any

from secondbrain.answer.context import build_context, estimate_tokens
from secondbrain.answer.prompt import NOT_FOUND, QUESTION_MAX_CHARS, SYSTEM_PROMPT, build_messages
from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import NoteHit, RelatedNote, SearchResult


def settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]


def hit(path: str, text: str) -> Hit:
    p = {"note_path": path, "heading_path": "T", "page": 3, "text": text, "asignatura": "X"}
    return Hit(0.5, p)


def one_note(text: str = "contenido") -> SearchResult:
    n = NoteHit("a/X.md", "X", 0.5, 0.5, (hit("a/X.md", text),), (), 3)
    return SearchResult([n], [])


def test_system_prompt_demands_citations_and_the_not_found_sentence() -> None:
    assert NOT_FOUND == "No lo encuentro en el vault."
    assert NOT_FOUND in SYSTEM_PROMPT
    assert "[S3]" in SYSTEM_PROMPT
    assert "FUENTES" in SYSTEM_PROMPT


def test_system_prompt_marks_related_notes_as_hints_not_evidence() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "pistas" in lowered and "evidencia" in lowered


def test_system_prompt_is_small() -> None:
    assert estimate_tokens(SYSTEM_PROMPT) <= 450


def test_messages_are_system_then_user_with_context_and_question(tmp_path: Path) -> None:
    s = settings(tmp_path)
    ctx = build_context(one_note("el semáforo es un contador"), s)
    system, user = build_messages("¿Qué es un semáforo?", ctx)
    assert (system.role, user.role) == ("system", "user")
    assert system.content == SYSTEM_PROMPT
    assert "el semáforo es un contador" in user.content
    assert user.content.rstrip().endswith("¿Qué es un semáforo?")


def test_an_empty_context_still_produces_a_valid_prompt(tmp_path: Path) -> None:
    ctx = build_context(SearchResult([], []), settings(tmp_path))
    _, user = build_messages("pregunta", ctx)
    assert "pregunta" in user.content


def test_very_long_questions_are_truncated(tmp_path: Path) -> None:
    ctx = build_context(one_note(), settings(tmp_path))
    _, user = build_messages("p" * 50_000, ctx)
    assert len(user.content) < QUESTION_MAX_CHARS + len(ctx.text) + 400


def test_the_whole_prompt_plus_the_answer_fits_in_the_context_window(tmp_path: Path) -> None:
    """Peor caso: chunks enormes, muchas relacionadas y una pregunta kilométrica."""
    s = settings(tmp_path)
    notes = [
        NoteHit(f"c/N{i}.md", f"N{i}", 0.5, 0.5, (hit(f"c/N{i}.md", "palabra " * 6000),), (), 9)
        for i in range(10)
    ]
    rel = [
        RelatedNote(f"r/R{i}.md", 1.0, ("c",), ("a",), "resumen " * 500, "H", None, "s" * 900)
        for i in range(30)
    ]
    ctx = build_context(SearchResult(notes, rel), s)
    messages = build_messages("¿" + "pregunta larga " * 5000 + "?", ctx)
    prompt_tokens = sum(estimate_tokens(m.content) for m in messages)
    assert prompt_tokens + s.llm_max_tokens <= s.llm_num_ctx


# --- ajustes tras ver respuestas reales del modelo -------------------------------


def test_the_prompt_forbids_writing_titles_pages_or_subjects_after_a_citation() -> None:
    assert "No escribas títulos de notas, páginas, asignaturas ni cursos" in SYSTEM_PROMPT


def test_the_prompt_gives_a_fixed_template_for_suggesting_nearby_notes() -> None:
    # Con la frase anterior el modelo la copiaba literalmente en la respuesta.
    assert "Podrías mirar:" in SYSTEM_PROMPT
    assert "Puedes añadir" not in SYSTEM_PROMPT


def test_the_prompt_forbids_extrapolating_beyond_the_sources() -> None:
    assert "No extrapoles" in SYSTEM_PROMPT


def test_the_prompt_asks_for_complete_structured_answers() -> None:
    assert "completa y bien estructurada" in SYSTEM_PROMPT
    assert "conciso" not in SYSTEM_PROMPT.lower()


def test_overview_questions_get_the_overview_instructions(tmp_path: Path) -> None:
    from secondbrain.answer.context import BuiltContext
    from secondbrain.answer.prompt import OVERVIEW_PROMPT

    overview = BuiltContext("FUENTES (evidencia):", (), 5, 0, "overview", ())
    system = build_messages("¿De qué trata?", overview)[0].content
    assert OVERVIEW_PROMPT in system and "visión general" in system
    normal = BuiltContext("FUENTES (evidencia):", (), 5, 0, "search", ())
    assert OVERVIEW_PROMPT not in build_messages("¿Qué es un hilo?", normal)[0].content


def test_the_overview_prompt_still_fits_the_window(tmp_path: Path) -> None:
    from secondbrain.answer.prompt import OVERVIEW_PROMPT

    assert estimate_tokens(SYSTEM_PROMPT + OVERVIEW_PROMPT) <= 650
