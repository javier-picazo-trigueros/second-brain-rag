from __future__ import annotations

from secondbrain.evals.golden import AnswerScore, GoldenQuestion
from secondbrain.evals.runner import run_golden


def _q(qid: str, kind: str = "concrete", **over: object) -> GoldenQuestion:
    base: dict[str, object] = {
        "id": qid,
        "kind": kind,
        "question": f"pregunta {qid}",
        "expect": ("Semáforos",),
        "acceptable": (),
        "expect_not_found": False,
    }
    base.update(over)
    return GoldenQuestion(**base)  # type: ignore[arg-type]


def test_run_golden_scores_each_question_and_summarises() -> None:
    questions = [_q("a"), _q("b", "trap", expect=(), expect_not_found=True)]
    retrieved = {"pregunta a": ["x/Semáforos.md"], "pregunta b": []}
    report = run_golden(questions, retrieve=lambda q: retrieved[q])
    rows = {r["id"]: r for r in report["rows"]}
    assert rows["a"]["recall"] == 1.0 and rows["a"]["noise"] == 0
    assert rows["b"]["noise"] == 0
    assert report["summary"]["TOTAL"]["n"] == 2.0
    assert "answer" not in rows["a"]


def test_run_golden_with_answers_adds_answer_metrics() -> None:
    answer = AnswerScore(
        chars=100, completion_tokens=40, citations=1, invalid_citations=0, bad_pages=0,
        not_found=False, warnings=(), retrieval_ms=100.0, first_token_ms=900.0, total_ms=3000.0,
    )  # fmt: skip
    report = run_golden([_q("a")], retrieve=lambda q: ["x/Semáforos.md"], answer=lambda q: answer)
    row = report["rows"][0]
    assert row["answer"]["chars"] == 100
    assert report["answers"]["mean_chars"] == 100.0
    assert report["answers"]["invalid_citations"] == 0
    assert report["answers"]["mean_total_ms"] == 3000.0


def test_run_golden_records_environment_note() -> None:
    report = run_golden([_q("a")], retrieve=lambda q: [], note="GPU compartida")
    assert report["note"] == "GPU compartida"


def test_run_golden_trap_answered_not_found_is_marked() -> None:
    answer = AnswerScore(
        chars=28, completion_tokens=8, citations=0, invalid_citations=0, bad_pages=0,
        not_found=True, warnings=(), retrieval_ms=1.0, first_token_ms=1.0, total_ms=2.0,
    )  # fmt: skip
    trap = _q("t", "trap", expect=(), expect_not_found=True)
    report = run_golden([trap], retrieve=lambda q: [], answer=lambda q: answer)
    assert report["rows"][0]["not_found_ok"] is True
    assert report["answers"]["traps_ok"] == 1.0
