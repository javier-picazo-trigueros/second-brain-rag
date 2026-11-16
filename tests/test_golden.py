from __future__ import annotations

from pathlib import Path

import pytest

from secondbrain.evals.golden import (
    AnswerScore,
    GoldenQuestion,
    load_golden,
    matches,
    render_comparison,
    score_answer,
    score_retrieval,
    summarize,
)

YAML = """
version: 1
questions:
  - id: q1
    kind: concrete
    question: "¿Qué es un semáforo?"
    expect: ["Semáforos", "Monitores|Sincronización"]
    acceptable: ["Libro"]
  - id: q2
    kind: trap
    question: "¿Receta de paella?"
    expect_not_found: true
"""


def _q(**over: object) -> GoldenQuestion:
    base: dict[str, object] = {
        "id": "q",
        "kind": "concrete",
        "question": "¿?",
        "expect": ("Semáforos", "Monitores|Sincronización"),
        "acceptable": ("Libro",),
        "expect_not_found": False,
    }
    base.update(over)
    return GoldenQuestion(**base)  # type: ignore[arg-type]


def test_load_golden_reads_questions(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text(YAML, encoding="utf-8")
    qs = load_golden(f)
    assert [q.id for q in qs] == ["q1", "q2"]
    assert qs[0].expect == ("Semáforos", "Monitores|Sincronización")
    assert qs[1].expect_not_found is True and qs[1].expect == ()


def test_load_golden_rejects_duplicate_ids(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text(YAML + YAML.split("questions:")[1], encoding="utf-8")
    with pytest.raises(ValueError, match="duplicad"):
        load_golden(f)


def test_load_golden_rejects_unknown_kind(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text(
        'version: 1\nquestions:\n  - {id: a, kind: rara, question: "x", expect: ["y"]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kind"):
        load_golden(f)


def test_load_golden_requires_expectation_unless_trap(tmp_path: Path) -> None:
    f = tmp_path / "g.yaml"
    f.write_text(
        'version: 1\nquestions:\n  - {id: a, kind: concrete, question: "x"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="expect"):
        load_golden(f)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("3º/SO/Semáforos.md", "semáforos", True),  # sin distinguir mayúsculas
        ("3º/SO/Semaforos.md", "Semáforos", True),  # ni acentos
        ("3º/SO/Monitores.md", "Hilos|Monitores", True),  # alternativas con |
        ("3º/SO/Otra.md", "Hilos|Monitores", False),
        ("3º/Tema 5 [MD].md", "Tema 5 [MD]", True),  # los corchetes son literales
    ],
)
def test_matches(path: str, pattern: str, expected: bool) -> None:
    assert matches(path, pattern) is expected


def test_score_retrieval_recall_and_precision() -> None:
    q = _q()
    s = score_retrieval(q, ["x/Semáforos.md", "x/Libro.md", "x/Ruido.md", "x/Ruido 2.md"])
    assert s.recall == 0.5  # solo "Semáforos" de las 2 expectativas
    assert s.precision == 0.5  # Semáforos y Libro de 4
    assert s.noise == 2
    assert s.top1_hit is True


def test_score_retrieval_top1_miss() -> None:
    s = score_retrieval(_q(), ["x/Ruido.md", "x/Semáforos.md"])
    assert s.top1_hit is False


def test_score_retrieval_empty_result() -> None:
    s = score_retrieval(_q(), [])
    assert (s.recall, s.precision, s.noise, s.top1_hit) == (0.0, 0.0, 0, False)


def test_trap_is_clean_when_nothing_is_retrieved() -> None:
    trap = _q(expect=(), acceptable=(), expect_not_found=True)
    assert score_retrieval(trap, []).noise == 0
    assert score_retrieval(trap, []).recall == 1.0  # nada que encontrar
    assert score_retrieval(trap, ["a.md", "b.md"]).noise == 2


def test_score_answer_extracts_metrics() -> None:
    a = score_answer(
        answer="Texto largo " * 10,
        warnings=("citas_no_verificadas",),
        invalid=("X",),
        bad_pages=(),
        citations=2,
        not_found=False,
        completion_tokens=120,
        retrieval_ms=150.0,
        first_token_ms=900.0,
        total_ms=4000.0,
    )
    assert isinstance(a, AnswerScore)
    assert a.chars == len("Texto largo " * 10)
    assert a.invalid_citations == 1 and a.citations == 2
    assert a.warnings == ("citas_no_verificadas",)


def test_summarize_averages_by_kind() -> None:
    rows = [
        {"kind": "concrete", "recall": 1.0, "precision": 0.5, "noise": 1, "top1_hit": True},
        {"kind": "concrete", "recall": 0.0, "precision": 0.5, "noise": 3, "top1_hit": False},
        {"kind": "trap", "recall": 1.0, "precision": 0.0, "noise": 2, "top1_hit": False},
    ]
    s = summarize(rows)
    assert s["concrete"]["recall"] == 0.5
    assert s["concrete"]["noise"] == 2.0
    assert s["concrete"]["n"] == 2
    assert s["TOTAL"]["n"] == 3


def test_render_comparison_shows_before_and_after() -> None:
    before = {"concrete": {"n": 2, "recall": 0.5, "precision": 0.4, "noise": 2.0, "top1_hit": 0.5}}
    after = {"concrete": {"n": 2, "recall": 0.9, "precision": 0.8, "noise": 0.5, "top1_hit": 1.0}}
    table = render_comparison(before, after)
    assert "concrete" in table
    assert "0,50" in table and "0,90" in table  # decimales con coma
