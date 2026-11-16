"""Preguntas de referencia: solo preguntas y rutas esperadas, nunca contenido de notas."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

KINDS = ("concrete", "overview_subject", "overview_topic", "cross", "trap")
_METRICS = ("recall", "precision", "noise", "top1_hit")


@dataclass(frozen=True, slots=True)
class GoldenQuestion:
    id: str
    kind: str
    question: str
    expect: tuple[str, ...]  # fragmentos de ruta; "a|b" = cualquiera de las dos alternativas
    acceptable: tuple[str, ...]  # rutas válidas pero no imprescindibles: no cuentan como ruido
    expect_not_found: bool


@dataclass(frozen=True, slots=True)
class RetrievalScore:
    recall: float  # fracción de expectativas cubiertas por alguna nota recuperada
    precision: float  # fracción de notas recuperadas que son esperadas o aceptables
    noise: int  # notas recuperadas que no son ni esperadas ni aceptables
    top1_hit: bool  # la primera nota es una esperada
    retrieved: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnswerScore:
    chars: int
    completion_tokens: int | None
    citations: int
    invalid_citations: int
    bad_pages: int
    not_found: bool
    warnings: tuple[str, ...]
    retrieval_ms: float
    first_token_ms: float | None
    total_ms: float


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def matches(path: str, pattern: str) -> bool:
    """¿La ruta contiene alguna de las alternativas del patrón? Sin mayúsculas ni acentos."""
    haystack = _norm(path)
    return any(_norm(alt) in haystack for alt in pattern.split("|") if alt)


def load_golden(path: Path) -> list[GoldenQuestion]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[GoldenQuestion] = []
    seen: set[str] = set()
    for raw in data.get("questions", []):
        qid = str(raw["id"])
        if qid in seen:
            raise ValueError(f"Id duplicado en el golden set: {qid}")
        seen.add(qid)
        kind = str(raw.get("kind", ""))
        if kind not in KINDS:
            raise ValueError(f"{qid}: kind debe ser uno de {', '.join(KINDS)} (es {kind!r})")
        expect = tuple(str(x) for x in raw.get("expect", ()))
        not_found = bool(raw.get("expect_not_found", False))
        if not expect and not not_found:
            raise ValueError(f"{qid}: falta `expect` (o `expect_not_found: true` en una trampa)")
        out.append(
            GoldenQuestion(
                id=qid,
                kind=kind,
                question=str(raw["question"]),
                expect=expect,
                acceptable=tuple(str(x) for x in raw.get("acceptable", ())),
                expect_not_found=not_found,
            )
        )
    return out


def score_retrieval(question: GoldenQuestion, retrieved: Sequence[str]) -> RetrievalScore:
    paths = tuple(retrieved)
    covered = sum(1 for e in question.expect if any(matches(p, e) for p in paths))
    recall = covered / len(question.expect) if question.expect else 1.0
    good = [
        p for p in paths if any(matches(p, e) for e in (*question.expect, *question.acceptable))
    ]
    precision = len(good) / len(paths) if paths else 0.0
    top1 = bool(paths) and any(matches(paths[0], e) for e in question.expect)
    return RetrievalScore(recall, precision, len(paths) - len(good), top1, paths)


def score_answer(
    *,
    answer: str,
    warnings: Sequence[str],
    invalid: Sequence[str],
    bad_pages: Sequence[object],
    citations: int,
    not_found: bool,
    completion_tokens: int | None,
    retrieval_ms: float,
    first_token_ms: float | None,
    total_ms: float,
) -> AnswerScore:
    return AnswerScore(
        chars=len(answer),
        completion_tokens=completion_tokens,
        citations=citations,
        invalid_citations=len(invalid),
        bad_pages=len(bad_pages),
        not_found=not_found,
        warnings=tuple(warnings),
        retrieval_ms=retrieval_ms,
        first_token_ms=first_token_ms,
        total_ms=total_ms,
    )


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    """Medias de las métricas de recuperación por tipo de pregunta, más el TOTAL."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["kind"]), []).append(row)
    groups["TOTAL"] = list(rows)
    summary: dict[str, dict[str, float]] = {}
    for kind, items in groups.items():
        entry: dict[str, float] = {"n": float(len(items))}
        for metric in _METRICS:
            entry[metric] = sum(float(r[metric]) for r in items) / len(items)
        summary[kind] = entry
    return summary


def _fmt(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def render_comparison(
    before: Mapping[str, Mapping[str, float]], after: Mapping[str, Mapping[str, float]]
) -> str:
    """Tabla Markdown antes → después por tipo de pregunta."""
    lines = [
        "| Tipo | n | Recall | Precisión | Ruido (notas) | Top-1 |",
        "|---|---|---|---|---|---|",
    ]
    for kind in after:
        b, a = before.get(kind), after[kind]
        cells = [kind, str(int(a["n"]))]
        for metric in _METRICS:
            now = _fmt(a[metric])
            cells.append(f"{_fmt(b[metric])} → {now}" if b else now)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
