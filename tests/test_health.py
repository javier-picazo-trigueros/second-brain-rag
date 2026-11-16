from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from secondbrain.api import health as health_module
from secondbrain.api.health import HealthChecker, gpu_memory
from secondbrain.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


def settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]


def ollama(models: list[str], loaded: list[dict[str, Any]] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.6"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": loaded or []})
        return httpx.Response(404)

    return handler


def checker(
    tmp_path: Path,
    handler: Handler,
    count: Callable[[], int] = lambda: 23236,
    **overrides: Any,
) -> HealthChecker:
    s = settings(tmp_path, **overrides)
    client = httpx.Client(base_url=s.ollama_url, transport=httpx.MockTransport(handler))
    return HealthChecker(s, client, count)


FULL = ["bge-m3:latest", "qwen2.5:7b"]


def test_everything_up_is_ok(tmp_path: Path) -> None:
    report = checker(tmp_path, ollama(FULL)).check()
    assert report.status == "ok"
    assert (report.ollama.ok, report.qdrant.ok, report.vault.ok) == (True, True, True)
    assert report.ollama.version == "0.40.6"
    assert report.qdrant.points == 23236
    assert report.hints == []


def test_models_are_reported_individually(tmp_path: Path) -> None:
    report = checker(tmp_path, ollama(FULL)).check()
    assert report.ollama.models == {"bge-m3": True, "qwen2.5:7b": True}


def test_a_missing_model_degrades_and_says_which_pull_to_run(tmp_path: Path) -> None:
    report = checker(tmp_path, ollama(["bge-m3:latest"])).check()
    assert report.status == "degraded"
    assert report.ollama.models["qwen2.5:7b"] is False
    assert any("ollama pull qwen2.5:7b" in h for h in report.hints)


def test_loaded_models_and_their_vram_are_reported(tmp_path: Path) -> None:
    loaded = [
        {"name": "qwen2.5:7b", "size_vram": 5_023_916_358, "expires_at": "2026-11-16T20:00:00Z"}
    ]
    report = checker(tmp_path, ollama(FULL, loaded)).check()
    assert report.ollama.loaded[0].name == "qwen2.5:7b"
    assert report.ollama.loaded[0].vram_mib == pytest.approx(4791.0, abs=1.0)


def test_ollama_down_is_reported_with_how_to_start_it(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    report = checker(tmp_path, down).check()
    assert report.status == "down"
    assert report.ollama.ok is False and report.ollama.models == {}
    assert any("ollama serve" in h for h in report.hints)


def test_qdrant_down_is_reported_with_how_to_start_it(tmp_path: Path) -> None:
    def broken() -> int:
        raise ConnectionError("sin conexión")

    report = checker(tmp_path, ollama(FULL), count=broken).check()
    assert report.status == "down"
    assert report.qdrant.ok is False
    assert any("tasks.ps1 up" in h for h in report.hints)


def test_a_missing_vault_is_reported(tmp_path: Path) -> None:
    s = settings(tmp_path)
    client = httpx.Client(base_url=s.ollama_url, transport=httpx.MockTransport(ollama(FULL)))
    vault = tmp_path / "desaparecido"
    # El vault se valida al crear Settings; aquí se simula que desaparece después.
    object.__setattr__(s, "vault_path", vault)
    report = HealthChecker(s, client, lambda: 1).check()
    assert report.vault.ok is False
    assert report.status == "degraded"
    assert any("BRAIN_VAULT_PATH" in h for h in report.hints)


def test_the_embedding_model_name_is_matched_without_the_tag(tmp_path: Path) -> None:
    report = checker(
        tmp_path, ollama(["bge-m3:latest", "qwen2.5:7b"]), embed_model="bge-m3"
    ).check()
    assert report.ollama.models["bge-m3"] is True


# --- memoria de la GPU -----------------------------------------------------------------------


def test_gpu_memory_parses_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="4915, 8188\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    gpu = gpu_memory()
    assert gpu is not None and (gpu.used_mib, gpu.total_mib) == (4915, 8188)


def test_gpu_memory_is_none_without_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr("subprocess.run", missing)
    assert gpu_memory() is None


def test_gpu_memory_is_none_when_the_command_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 9, stdout="", stderr="error")

    monkeypatch.setattr("subprocess.run", failing)
    assert gpu_memory() is None


def test_health_includes_gpu_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_module, "gpu_memory", lambda: health_module.GpuMemory(100, 8188))
    report = checker(tmp_path, ollama(FULL)).check()
    assert report.gpu is not None and report.gpu.total_mib == 8188
