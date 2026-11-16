from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer

from secondbrain.answer.pipeline import DoneEvent, TokenEvent
from secondbrain.api.app import AppServices
from secondbrain.evals.golden import (
    AnswerScore,
    load_golden,
    render_comparison,
    score_answer,
)
from secondbrain.evals.runner import run_golden

golden_app = typer.Typer(no_args_is_help=True, help="Preguntas de referencia (evals/golden)")

_DEFAULT_FILE = Path("evals/golden/golden.local.yaml")


def gpu_note() -> str:
    """Estado de la GPU en el momento de medir (la latencia depende de si está compartida)."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return "GPU: nvidia-smi no disponible"
    query = ["--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader"]
    try:
        out = subprocess.run(
            [exe, *query], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return f"GPU: nvidia-smi falló ({type(exc).__name__})"
    return f"GPU al medir (uso, memoria usada, total): {out}"


def _retrieve(services: AppServices) -> Any:
    def retrieve(question: str) -> list[str]:
        _, context = services.pipeline.plan(question)
        return [s.path for s in context.sources if s.kind == "evidence"]

    return retrieve


def _answer(services: AppServices) -> Any:
    def answer(question: str) -> AnswerScore:
        text: list[str] = []
        done: DoneEvent | None = None
        for event in services.pipeline.ask(question):
            if isinstance(event, TokenEvent):
                text.append(event.text)
            elif isinstance(event, DoneEvent):
                done = event
        if done is None:
            raise RuntimeError(f"La respuesta a {question!r} terminó sin evento final")
        return score_answer(
            answer=done.answer,
            warnings=done.warnings,
            invalid=done.invalid,
            bad_pages=done.bad_pages,
            citations=len(done.citations),
            not_found=done.not_found,
            completion_tokens=done.completion_tokens,
            retrieval_ms=done.timings.retrieval_ms,
            first_token_ms=done.timings.first_token_ms,
            total_ms=done.timings.total_ms,
        )

    return answer


@golden_app.command("run")
def run(
    file: Annotated[Path, typer.Option(help="Fichero de preguntas")] = _DEFAULT_FILE,
    out: Annotated[Path | None, typer.Option(help="Dónde guardar el informe JSON")] = None,
    answers: Annotated[
        bool, typer.Option(help="Generar también las respuestas (usa el LLM)")
    ] = False,
    note: Annotated[str, typer.Option(help="Nota para el informe (p. ej. GPU compartida)")] = "",
) -> None:
    """Mide la recuperación (y, con --answers, las respuestas) sobre el índice real."""
    from secondbrain.api.main import build_services  # import tardío: carga fastembed y qdrant

    services = build_services()
    questions = load_golden(file)
    report = run_golden(
        questions,
        retrieve=_retrieve(services),
        answer=_answer(services) if answers else None,
        note=f"{note} | {gpu_note()}".strip(" |"),
    )
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for kind, values in report["summary"].items():
        typer.echo(
            f"{kind:18s} n={int(values['n']):2d} recall={values['recall']:.2f} "
            f"precision={values['precision']:.2f} ruido={values['noise']:.1f} "
            f"top1={values['top1_hit']:.2f}"
        )
    if "answers" in report:
        typer.echo(json.dumps(report["answers"], ensure_ascii=False))


@golden_app.command("compare")
def compare(before: Path, after: Path) -> None:
    """Tabla antes → después entre dos informes."""
    b = json.loads(before.read_text(encoding="utf-8"))
    a = json.loads(after.read_text(encoding="utf-8"))
    typer.echo(render_comparison(b["summary"], a["summary"]))
