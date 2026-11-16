from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from secondbrain.config import Settings

_NS_PER_MS = 1_000_000.0


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class Delta:
    """Fragmento de texto de la respuesta, tal como llega del modelo."""

    text: str


@dataclass(frozen=True, slots=True)
class Finished:
    """Fin de la generación, con las cifras medidas por el propio modelo."""

    prompt_tokens: int
    completion_tokens: int
    load_ms: float
    prompt_eval_ms: float
    eval_ms: float
    truncated: bool  # el modelo se quedó sin `num_predict` antes de terminar


class LLMError(RuntimeError):
    """Fallo del modelo con un mensaje pensado para mostrarse al usuario."""


class LLM(Protocol):
    def stream_chat(self, messages: Sequence[Message]) -> Iterator[Delta | Finished]: ...


class OllamaLLM:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=settings.ollama_url, timeout=httpx.Timeout(300.0, connect=10.0)
        )
        self._url = settings.ollama_url
        self._model = settings.llm_model
        self._keep_alive = settings.llm_keep_alive
        self._options: dict[str, Any] = {
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
        }

    def stream_chat(self, messages: Sequence[Message]) -> Iterator[Delta | Finished]:
        payload = {
            "model": self._model,
            "stream": True,
            "keep_alive": self._keep_alive,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": self._options,
        }
        try:
            with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code != 200:
                    response.read()
                    raise self._http_error(response)
                yield from self._parse(response)
        except httpx.TransportError as exc:
            raise LLMError(
                f"Ollama no responde en {self._url}: arráncalo con `ollama serve`."
            ) from exc

    def _parse(self, response: httpx.Response) -> Iterator[Delta | Finished]:
        for line in response.iter_lines():
            if not line.strip():
                continue
            data = json.loads(line)
            if "error" in data:
                raise LLMError(f"Ollama devolvió un error durante la respuesta: {data['error']}")
            text = data.get("message", {}).get("content", "")
            if text:
                yield Delta(text)
            if data.get("done"):
                yield Finished(
                    prompt_tokens=int(data.get("prompt_eval_count", 0)),
                    completion_tokens=int(data.get("eval_count", 0)),
                    load_ms=data.get("load_duration", 0) / _NS_PER_MS,
                    prompt_eval_ms=data.get("prompt_eval_duration", 0) / _NS_PER_MS,
                    eval_ms=data.get("eval_duration", 0) / _NS_PER_MS,
                    truncated=data.get("done_reason") == "length",
                )
                return
        raise LLMError("La respuesta de Ollama fue interrumpida antes de terminar.")

    def _http_error(self, response: httpx.Response) -> LLMError:
        if response.status_code == 404:
            return LLMError(
                f"Ollama no tiene el modelo '{self._model}': ejecuta `ollama pull {self._model}`."
            )
        try:
            detail = str(response.json().get("error", response.text))
        except ValueError:
            detail = response.text
        return LLMError(f"Ollama respondió {response.status_code}: {detail}")
