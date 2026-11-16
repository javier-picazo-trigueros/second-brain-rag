from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)


def _embedder(tmp_path: Path, handler: Handler, **overrides: Any) -> OllamaEmbedder:
    settings = Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]
    client = httpx.Client(base_url=settings.ollama_url, transport=httpx.MockTransport(handler))
    return OllamaEmbedder(settings, client=client)


def _ok(request: httpx.Request) -> httpx.Response:
    texts = json.loads(request.content)["input"]
    return httpx.Response(200, json={"embeddings": [[float(len(t)), 1.0] for t in texts]})


def test_embed_documents_batches_and_keeps_order(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(json.loads(request.content)["input"]))
        return _ok(request)

    emb = _embedder(tmp_path, handler, embed_batch_size=16)
    texts = ["x" * i for i in range(1, 41)]
    vectors = emb.embed_documents(texts)
    assert calls == [16, 16, 8]
    assert [v[0] for v in vectors] == [float(i) for i in range(1, 41)]


def test_embed_documents_of_empty_list_makes_no_request(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería haber peticiones")

    assert _embedder(tmp_path, handler).embed_documents([]) == []


def test_request_payload_uses_model_and_keep_alive(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["path"] = request.url.path
        return _ok(request)

    _embedder(tmp_path, handler, embed_keep_alive="45s").embed_query("hola")
    assert seen["path"] == "/api/embed"
    assert seen["model"] == "bge-m3"
    assert seen["keep_alive"] == "45s"
    assert seen["input"] == ["hola"]


def test_cpu_mode_disables_gpu_layers(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    _embedder(tmp_path, handler, embed_on_cpu=True).embed_query("hola")
    assert seen["options"] == {"num_gpu": 0}


def test_gpu_mode_sends_no_options(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    _embedder(tmp_path, handler, embed_on_cpu=False).embed_query("hola")
    assert "options" not in seen


def test_dimension_is_the_vector_length(tmp_path: Path) -> None:
    assert _embedder(tmp_path, _ok).dimension() == 2


def test_transient_server_errors_are_retried(tmp_path: Path) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return _ok(request)

    assert _embedder(tmp_path, handler).embed_query("hola") == [4.0, 1.0]
    assert attempts["n"] == 3


def test_connection_errors_are_retried_then_raised(tmp_path: Path) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("Ollama no responde")

    with pytest.raises(httpx.ConnectError):
        _embedder(tmp_path, handler).embed_query("hola")
    assert attempts["n"] == 3


def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(404, json={"error": "model 'bge-m3' not found"})

    with pytest.raises(httpx.HTTPStatusError):
        _embedder(tmp_path, handler).embed_query("hola")
    assert attempts["n"] == 1


def test_mismatched_embedding_count_is_an_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    with pytest.raises(RuntimeError, match=r"2 textos.*1 embeddings"):
        _embedder(tmp_path, handler).embed_documents(["a", "b"])
