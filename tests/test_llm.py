from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from secondbrain.answer.llm import Delta, Finished, LLMError, Message, OllamaLLM
from secondbrain.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]

MESSAGES = [Message("system", "Eres un asistente."), Message("user", "¿Qué es un semáforo?")]


def _llm(tmp_path: Path, handler: Handler, **overrides: Any) -> OllamaLLM:
    settings = Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]
    client = httpx.Client(base_url=settings.ollama_url, transport=httpx.MockTransport(handler))
    return OllamaLLM(settings, client=client)


def _ndjson(*objects: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objects)


def _chunk(text: str) -> dict[str, Any]:
    return {"message": {"role": "assistant", "content": text}, "done": False}


def _done(**extra: Any) -> dict[str, Any]:
    final = {
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "load_duration": 6_000_000,
        "prompt_eval_count": 120,
        "prompt_eval_duration": 50_000_000,
        "eval_count": 3,
        "eval_duration": 60_000_000,
    }
    return {**final, **extra}


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, content=_ndjson(_chunk("Un "), _chunk("semá"), _chunk("foro"), _done())
    )


def test_stream_yields_deltas_in_order_then_the_final_stats(tmp_path: Path) -> None:
    events = list(_llm(tmp_path, _ok).stream_chat(MESSAGES))
    assert [e.text for e in events if isinstance(e, Delta)] == ["Un ", "semá", "foro"]
    final = events[-1]
    assert isinstance(final, Finished)
    assert (final.prompt_tokens, final.completion_tokens) == (120, 3)
    assert (final.load_ms, final.prompt_eval_ms, final.eval_ms) == (6.0, 50.0, 60.0)
    assert final.truncated is False


def test_empty_deltas_are_skipped(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(_chunk(""), _chunk("hola"), _done()))

    events = list(_llm(tmp_path, handler).stream_chat(MESSAGES))
    assert [e.text for e in events if isinstance(e, Delta)] == ["hola"]


def test_request_payload(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["path"] = request.url.path
        return _ok(request)

    list(_llm(tmp_path, handler).stream_chat(MESSAGES))
    assert seen["path"] == "/api/chat"
    assert (seen["model"], seen["stream"], seen["keep_alive"]) == ("qwen2.5:7b", True, "10m")
    assert seen["options"] == {"num_ctx": 16384, "num_predict": 1024, "temperature": 0.2}
    assert seen["messages"] == [
        {"role": "system", "content": "Eres un asistente."},
        {"role": "user", "content": "¿Qué es un semáforo?"},
    ]


def test_payload_follows_settings(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    llm = _llm(tmp_path, handler, llm_model="otro:1b", llm_num_ctx=4096, llm_max_tokens=200)
    list(llm.stream_chat(MESSAGES))
    assert seen["model"] == "otro:1b"
    assert seen["options"]["num_ctx"] == 4096 and seen["options"]["num_predict"] == 200


def test_a_cut_off_answer_is_flagged_as_truncated(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(_chunk("texto"), _done(done_reason="length")))

    final = list(_llm(tmp_path, handler).stream_chat(MESSAGES))[-1]
    assert isinstance(final, Finished) and final.truncated is True


def test_missing_model_tells_which_pull_to_run(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'qwen2.5:7b' not found"})

    with pytest.raises(LLMError, match=r"ollama pull qwen2.5:7b"):
        list(_llm(tmp_path, handler).stream_chat(MESSAGES))


def test_unreachable_ollama_tells_how_to_start_it(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    with pytest.raises(LLMError, match=r"Ollama no responde.*ollama serve"):
        list(_llm(tmp_path, handler).stream_chat(MESSAGES))


def test_server_errors_are_reported_with_their_status(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "runner caído"})

    with pytest.raises(LLMError, match=r"500.*runner caído"):
        list(_llm(tmp_path, handler).stream_chat(MESSAGES))


def test_an_error_in_the_middle_of_the_stream_is_raised(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(_chunk("par"), {"error": "CUDA error"}))

    gen = _llm(tmp_path, handler).stream_chat(MESSAGES)
    assert next(gen) == Delta("par")
    with pytest.raises(LLMError, match="CUDA error"):
        next(gen)


def test_a_stream_that_ends_without_done_is_an_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(_chunk("par")))

    with pytest.raises(LLMError, match="interrumpida"):
        list(_llm(tmp_path, handler).stream_chat(MESSAGES))


def test_a_per_request_token_limit_overrides_the_default(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    list(_llm(tmp_path, handler).stream_chat(MESSAGES, max_tokens=2000))
    assert seen["options"]["num_predict"] == 2000
    assert seen["options"]["num_ctx"] == 16384  # el resto de opciones no cambia
