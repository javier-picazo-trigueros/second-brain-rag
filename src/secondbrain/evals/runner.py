from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from secondbrain.evals.golden import (
    AnswerScore,
    GoldenQuestion,
    score_retrieval,
    summarize,
)

Retrieve = Callable[[str], Sequence[str]]
Answer = Callable[[str], AnswerScore]


def run_golden(
    questions: Sequence[GoldenQuestion],
    *,
    retrieve: Retrieve,
    answer: Answer | None = None,
    note: str = "",
    families: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Evalúa cada pregunta. `retrieve` devuelve las rutas de evidencia que verá el modelo;
    `answer` (opcional, usa el LLM) devuelve las métricas de la respuesta."""
    rows: list[dict[str, Any]] = []
    answers: list[tuple[GoldenQuestion, AnswerScore]] = []
    for q in questions:
        score = score_retrieval(q, retrieve(q.question), families)
        row: dict[str, Any] = {
            "id": q.id,
            "kind": q.kind,
            "recall": score.recall,
            "precision": score.precision,
            "noise": score.noise,
            "top1_hit": score.top1_hit,
            "retrieved": list(score.retrieved),
        }
        if (
            answer is not None and q.kind != "notes"
        ):  # los apuntes tardan minutos: solo recuperación
            scored = answer(q.question)
            row["answer"] = dataclasses.asdict(scored)
            if q.expect_not_found:
                row["not_found_ok"] = scored.not_found
            answers.append((q, scored))
        rows.append(row)

    report: dict[str, Any] = {"note": note, "rows": rows, "summary": summarize(rows)}
    if answers:
        report["answers"] = _summarize_answers(answers)
    return report


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarize_answers(items: Sequence[tuple[GoldenQuestion, AnswerScore]]) -> dict[str, float]:
    scores = [a for _, a in items]
    traps = [a for q, a in items if q.expect_not_found]
    firsts = [a.first_token_ms for a in scores if a.first_token_ms is not None]
    return {
        "mean_chars": _mean([float(a.chars) for a in scores]),
        "mean_completion_tokens": _mean(
            [float(a.completion_tokens) for a in scores if a.completion_tokens is not None]
        ),
        "citations": float(sum(a.citations for a in scores)),
        "invalid_citations": float(sum(a.invalid_citations for a in scores)),
        "mean_retrieval_ms": _mean([a.retrieval_ms for a in scores]),
        "mean_first_token_ms": _mean(firsts),
        "mean_total_ms": _mean([a.total_ms for a in scores]),
        "traps_ok": _mean([1.0 if a.not_found else 0.0 for a in traps]) if traps else 1.0,
    }
