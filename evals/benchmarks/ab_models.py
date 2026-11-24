"""Compara modelos de Ollama sobre las preguntas del golden: tiempo, tokens, avisos y VRAM.

Uso (desde la raíz, con Ollama y Qdrant arrancados; un modelo cargado cada vez):

    python evals/benchmarks/ab_models.py --golden evals/golden/golden.local.yaml \
        --models qwen2.5:7b qwen3:8b --ids id-pregunta-1 id-pregunta-2 \
        --out evals/results/ab_modelos.json

Cada pareja modelo-pregunta se ejecuta `--repeat` veces con la misma semilla, el modelo ya caliente
y los demás descargados. El resultado (con texto de tus notas) va a `evals/results/`, ignorado por
git. Para los modelos cuyo nombre empieza por un prefijo de `--no-think` (Qwen3 por defecto) se
desactiva el razonamiento, que si no consume el tope de salida.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from secondbrain.answer.llm import OllamaLLM
from secondbrain.answer.pipeline import DoneEvent, ErrorEvent
from secondbrain.api.main import build_services
from secondbrain.config import load_settings
from secondbrain.evals.golden import load_golden

_SAMPLE_SECONDS = 1.0


def gpu_sample() -> tuple[int, int] | None:
    """(MiB de VRAM usados, % de utilización) según nvidia-smi, o None si no está disponible."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        used, util = (int(x.strip()) for x in out.strip().splitlines()[0].split(","))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return used, util


def keep_awake() -> None:
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # continuo + sistema requerido


def pinned_client(base_url: str, seed: int, think_off: bool) -> httpx.Client:
    """Cliente cuyo cuerpo de petición lleva siempre la misma semilla (y sin razonamiento)."""

    def hook(request: httpx.Request) -> None:
        body = json.loads(request.content)
        body["options"]["seed"] = seed
        if think_off:
            body["think"] = False
        request._content = json.dumps(body, ensure_ascii=False).encode()
        request.stream = httpx.ByteStream(request._content)
        request.headers["content-length"] = str(len(request._content))

    return httpx.Client(base_url=base_url, timeout=600, event_hooks={"request": [hook]})


def run_one(pipeline: Any, question: str) -> dict[str, Any]:
    samples: list[tuple[int, int]] = []
    stop = threading.Event()

    def monitor() -> None:
        while not stop.is_set():
            sample = gpu_sample()
            if sample is not None:
                samples.append(sample)
            stop.wait(_SAMPLE_SECONDS)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.perf_counter()
    row: dict[str, Any] = {}
    try:
        done: DoneEvent | None = None
        errors: list[str] = []
        for event in pipeline.ask(question):
            if isinstance(event, DoneEvent):
                done = event
            elif isinstance(event, ErrorEvent):
                errors.append(event.message)
        row.update(done=asdict(done) if done else None, errors=errors)
    finally:
        row["wall_seconds"] = round(time.perf_counter() - started, 2)
        stop.set()
        thread.join(timeout=_SAMPLE_SECONDS + 10)
    row["peak_vram_mib"] = max((s[0] for s in samples), default=None)
    row["mean_gpu_utilization"] = (
        round(statistics.mean(s[1] for s in samples), 1) if samples else None
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--ids", nargs="+", required=True, help="ids de las preguntas del golden")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--no-think", nargs="*", default=["qwen3"], help="prefijos sin razonamiento"
    )
    args = parser.parse_args()

    keep_awake()
    settings = load_settings()
    questions = {q.id: q for q in load_golden(args.golden)}
    missing = [i for i in args.ids if i not in questions]
    if missing:
        parser.error(f"ids que no están en el golden: {', '.join(missing)}")
    services = build_services(settings)
    pipeline = services.pipeline
    api = httpx.Client(base_url=settings.ollama_url, timeout=600)
    report: dict[str, Any] = {"seed": args.seed, "baseline_gpu": gpu_sample(), "rows": []}
    try:
        for model in args.models:
            for other in args.models:  # un solo modelo cargado cada vez
                if other != model:
                    api.post(
                        "/api/generate", json={"model": other, "keep_alive": 0}
                    ).raise_for_status()
            think_off = any(model.startswith(prefix) for prefix in args.no_think)
            client = pinned_client(settings.ollama_url, args.seed, think_off)
            pipeline._llm = OllamaLLM(
                settings.model_copy(update={"llm_model": model}), client=client
            )  # type: ignore[attr-defined]
            for repeat in range(1, args.repeat + 1):
                for qid in args.ids:
                    row = {"id": qid, "model": model, "repeat": repeat}
                    row.update(run_one(pipeline, questions[qid].question))
                    report["rows"].append(row)
                    done = row.get("done") or {}
                    print(
                        f"{model} {qid} #{repeat}: {row['wall_seconds']} s, "
                        f"{done.get('completion_tokens')} tokens, {done.get('warnings')}, "
                        f"VRAM máx. {row['peak_vram_mib']} MiB",
                        flush=True,
                    )
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            client.close()
            api.post("/api/generate", json={"model": model, "keep_alive": 0}).raise_for_status()
    finally:
        api.close()


if __name__ == "__main__":
    main()
