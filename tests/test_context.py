from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from secondbrain.answer.context import CHARS_PER_TOKEN, build_context, estimate_tokens
from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import NoteHit, RelatedNote, SearchResult


def settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]


def chunk(path: str, text: str, page: int | None = None, heading: str = "Tema") -> Hit:
    payload = {
        "note_path": path,
        "note_title": path.rsplit("/", 1)[-1][:-3],
        "heading_path": heading,
        "page": page,
        "text": text,
        "asignatura": "SISTEMAS",
        "curso": "2º",
    }
    return Hit(0.5, payload)


def note(path: str, *chunks: Hit, score: float = 0.5) -> NoteHit:
    title = path.rsplit("/", 1)[-1][:-3]
    return NoteHit(path, title, score, score, tuple(chunks), (), 5)


def related(path: str, resumen: str | None = "Resumen.", snippet: str | None = None) -> RelatedNote:
    return RelatedNote(path, 1.0, ("c1",), ("a.md",), resumen, "H", None, snippet)


def result(notes: list[NoteHit], rel: list[RelatedNote] | None = None) -> SearchResult:
    return SearchResult(notes, rel or [])


# --- estimación de tokens ---------------------------------------------------------------------


def test_estimate_is_conservative_chars_over_three() -> None:
    assert CHARS_PER_TOKEN == 3.0
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 300) == 100
    assert estimate_tokens("a" * 301) == 101


def test_estimate_never_underestimates_the_measured_ratio() -> None:
    # Medido con Ollama sobre chunks reales: entre 3,29 y 3,85 caracteres por token.
    assert estimate_tokens("x" * 3290) >= 3290 / 3.29


# --- contenido del contexto -------------------------------------------------------------------


def test_main_chunks_appear_in_rank_order_with_label_heading_and_page(tmp_path: Path) -> None:
    r = result(
        [
            note("1º/SO/Semáforos.md", chunk("1º/SO/Semáforos.md", "texto uno", 7, "Monitores")),
            note("2º/CAR/OpenMP.md", chunk("2º/CAR/OpenMP.md", "texto dos")),
        ]
    )
    ctx = build_context(r, settings(tmp_path))
    assert ctx.text.index("[[Semáforos]]") < ctx.text.index("[[OpenMP]]")
    assert "Monitores" in ctx.text and "p. 7" in ctx.text
    assert "texto uno" in ctx.text and "SISTEMAS" in ctx.text
    assert [s.label for s in ctx.sources] == ["Semáforos", "OpenMP"]
    assert all(s.kind == "evidence" for s in ctx.sources)


def test_pages_of_the_included_chunks_are_recorded(tmp_path: Path) -> None:
    chunks = (chunk("a/X.md", "uno", 7), chunk("a/X.md", "dos", 9), chunk("a/X.md", "tres"))
    ctx = build_context(result([note("a/X.md", *chunks)]), settings(tmp_path))
    assert ctx.sources[0].pages == (7, 9)


def test_empty_result_gives_an_empty_context(tmp_path: Path) -> None:
    ctx = build_context(result([]), settings(tmp_path))
    assert (ctx.text, ctx.sources, ctx.tokens, ctx.dropped_notes) == ("", (), 0, 0)


def test_notes_with_the_same_title_are_told_apart_by_their_folder(tmp_path: Path) -> None:
    r = result(
        [
            note("1º/IA/Apuntes.md", chunk("1º/IA/Apuntes.md", "a")),
            note("2º/IA/Apuntes.md", chunk("2º/IA/Apuntes.md", "b")),
            note("3º/IA/Único.md", chunk("3º/IA/Único.md", "c")),
        ]
    )
    labels = [s.label for s in build_context(r, settings(tmp_path)).sources]
    assert labels == ["1º/IA/Apuntes", "2º/IA/Apuntes", "Único"]


# --- presupuesto ------------------------------------------------------------------------------


@pytest.mark.parametrize("budget", [900, 2000, 4500])
def test_the_context_never_exceeds_the_budget(tmp_path: Path, budget: int) -> None:
    notes = [
        note(f"c/N{i}.md", *(chunk(f"c/N{i}.md", "palabra " * 250) for _ in range(2)))
        for i in range(8)
    ]
    rel = [related(f"r/R{i}.md", "resumen " * 100) for i in range(8)]
    s = settings(tmp_path, context_budget_tokens=budget, related_budget_tokens=300)
    ctx = build_context(result(notes, rel), s)
    assert 0 < ctx.tokens <= budget
    assert estimate_tokens(ctx.text) <= budget


def test_an_oversized_first_chunk_is_truncated_not_dropped(tmp_path: Path) -> None:
    big = "Una frase de relleno. " * 4000
    s = settings(tmp_path, context_budget_tokens=1000, related_budget_tokens=0)
    ctx = build_context(result([note("a/X.md", chunk("a/X.md", big))]), s)
    assert ctx.tokens <= 1000
    assert ctx.sources[0].truncated is True
    assert "[…]" in ctx.text


def test_notes_that_no_longer_fit_are_dropped_and_counted(tmp_path: Path) -> None:
    notes = [note(f"c/N{i}.md", chunk(f"c/N{i}.md", "palabra " * 300)) for i in range(10)]
    s = settings(tmp_path, context_budget_tokens=1500, related_budget_tokens=0)
    ctx = build_context(result(notes), s)
    assert 0 < len(ctx.sources) < 10
    assert ctx.dropped_notes == 10 - len(ctx.sources)
    assert [x.path for x in ctx.sources] == [f"c/N{i}.md" for i in range(len(ctx.sources))]


def test_truncation_prefers_a_paragraph_boundary(tmp_path: Path) -> None:
    text = "\n\n".join(f"Párrafo número {i} " + "x" * 200 for i in range(40))
    s = settings(tmp_path, context_budget_tokens=700, related_budget_tokens=0)
    ctx = build_context(result([note("a/X.md", chunk("a/X.md", text))]), s)
    body = ctx.text.split("[…]")[0].rstrip()
    assert body.endswith("x" * 200)


# --- relacionadas como pistas -----------------------------------------------------------------


def test_related_notes_are_hints_with_their_summary(tmp_path: Path) -> None:
    r = result([note("a/X.md", chunk("a/X.md", "texto"))], [related("b/Y.md", "Resumen de Y.")])
    ctx = build_context(r, settings(tmp_path))
    hint = next(s for s in ctx.sources if s.path == "b/Y.md")
    assert hint.kind == "hint"
    assert "[[Y]]" in ctx.text and "Resumen de Y." in ctx.text
    assert ctx.text.index("[[X]]") < ctx.text.index("[[Y]]")


def test_related_falls_back_to_the_snippet_and_then_to_the_title(tmp_path: Path) -> None:
    rel = [related("b/Y.md", None, "fragmento de Y"), related("b/Z.md", None, None)]
    ctx = build_context(result([note("a/X.md", chunk("a/X.md", "t"))], rel), settings(tmp_path))
    assert "fragmento de Y" in ctx.text
    assert "[[Z]]" in ctx.text


def test_related_stay_within_their_own_budget(tmp_path: Path) -> None:
    rel = [related(f"r/R{i}.md", "resumen " * 80) for i in range(20)]
    s = settings(tmp_path, context_budget_tokens=4500, related_budget_tokens=400)
    ctx = build_context(result([note("a/X.md", chunk("a/X.md", "t" * 100))], rel), s)
    hints = [x for x in ctx.sources if x.kind == "hint"]
    assert 0 < len(hints) < 20
    hint_part = ctx.text.split("NOTAS RELACIONADAS", 1)[1]
    assert estimate_tokens(hint_part) <= 400


def test_zero_related_budget_omits_the_section(tmp_path: Path) -> None:
    s = settings(tmp_path, related_budget_tokens=0)
    ctx = build_context(result([note("a/X.md", chunk("a/X.md", "t"))], [related("b/Y.md")]), s)
    assert "NOTAS RELACIONADAS" not in ctx.text
    assert all(x.kind == "evidence" for x in ctx.sources)
