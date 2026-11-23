"""Mide el modo apuntes con el modelo real: partes, llamadas al modelo, tiempo, citas y cortes.

Uso (desde la raíz, con Ollama y Qdrant arrancados):

    python evals/benchmarks/measure_notes.py --out evals/results/notes_before.json \
        "apuntes del tema 2 de <asignatura>" "apuntes del tema 5 de <otra>"

Cada pregunta se ejecuta una vez. Se envuelve el LLM para registrar cada llamada (`Finished`), de
modo que sirve igual con y sin continuación automática: las llamadas de más que partes son
continuaciones y una parte cuya última llamada termina cortada es un corte sin resolver.
El JSON guarda también la respuesta completa (`answer`) y el texto que escribió el modelo en cada
llamada (`calls[].text`), para revisar a mano cómo empalma una continuación. `--part-max-tokens`
baja el tope de salida por parte y provoca cortes reales. Los resultados contienen texto de tus
notas: `evals/results/` está ignorado por git; no los muevas a un sitio versionado.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from secondbrain.answer.llm import Delta, Finished, Message
from secondbrain.answer.pipeline import DoneEvent, ErrorEvent, ProgressEvent, TokenEvent
from secondbrain.api.main import build_services
from secondbrain.config import load_settings


class RecordingLLM:
    """Delegado que anota si cada llamada terminó cortada y cuántos tokens escribió."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    def stream_chat(
        self, messages: Sequence[Message], max_tokens: int | None = None
    ) -> Iterator[Delta | Finished]:
        started = time.perf_counter()
        pieces: list[str] = []
        for item in self._inner.stream_chat(messages, max_tokens):
            if isinstance(item, Delta):
                pieces.append(item.text)
            elif isinstance(item, Finished):
                self.calls.append(
                    {
                        "truncated": item.truncated,
                        "tokens": item.completion_tokens,
                        "seconds": round(time.perf_counter() - started, 1),
                        "text": "".join(pieces),  # lo que escribió el modelo en esta llamada
                    }
                )
            yield item


def measure(question: str, part_max_tokens: int | None = None) -> dict[str, Any]:
    settings = load_settings()
    if (
        part_max_tokens is not None
    ):  # un tope bajo provoca cortes reales para probar la continuación
        settings = settings.model_copy(update={"notes_part_max_tokens": part_max_tokens})
    services = build_services(settings)
    pipeline = services.pipeline
    recorder = RecordingLLM(pipeline._llm)  # medición
    pipeline._llm = recorder  # type: ignore[attr-defined]
    start = time.perf_counter()
    marks: list[int] = []
    parts_total = 0
    done: DoneEvent | None = None
    error: str | None = None
    for event in pipeline.ask(question):
        if isinstance(event, ProgressEvent):
            marks.append(len(recorder.calls))
            parts_total = event.total
            elapsed = time.perf_counter() - start
            print(f"  parte {event.part}/{event.total} ({elapsed:.0f} s)", flush=True)
        elif isinstance(event, DoneEvent):
            done = event
        elif isinstance(event, ErrorEvent):
            error = event.message
        elif isinstance(event, TokenEvent):
            pass
    marks.append(len(recorder.calls))
    per_part = [recorder.calls[a:b] for a, b in pairwise(marks)]
    return {
        "question": question,
        "seconds": round(time.perf_counter() - start, 1),
        "parts": parts_total,
        "model_calls": len(recorder.calls),
        "continuations": max(0, len(recorder.calls) - parts_total),
        "cut_calls": sum(1 for c in recorder.calls if c["truncated"]),
        "unresolved_cuts": sum(1 for p in per_part if p and p[-1]["truncated"]),
        "citations": len(done.citations) if done else 0,
        "invalid_citations": len(done.invalid) if done else 0,
        "warnings": list(done.warnings) if done else [],
        "answer_chars": len(done.answer) if done else 0,
        "error": error,
        "answer": done.answer if done else "",
        "calls": recorder.calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--part-max-tokens", type=int, default=None, help="tope de salida por parte"
    )
    args = parser.parse_args()
    results = [measure(q, args.part_max_tokens) for q in args.questions]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        print(
            f"{r['question']!r}: {r['seconds']} s, {r['parts']} partes, "
            f"{r['model_calls']} llamadas, {r['continuations']} continuaciones, "
            f"{r['cut_calls']} cortes ({r['unresolved_cuts']} sin resolver), "
            f"{r['citations']} citas ({r['invalid_citations']} no verificadas), {r['warnings']}"
        )


if __name__ == "__main__":
    main()
