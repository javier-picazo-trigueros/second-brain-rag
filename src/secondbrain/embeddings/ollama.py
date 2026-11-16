from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from secondbrain.config import Settings


def _is_transient(exc: BaseException) -> bool:
    """Reintentar errores de red y 5xx; un 4xx (p. ej. modelo inexistente) no se arregla solo."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


class OllamaEmbedder:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=settings.ollama_url, timeout=120.0)
        self._model = settings.embed_model
        self._batch = settings.embed_batch_size
        self._keep_alive = settings.embed_keep_alive
        self._cpu = settings.embed_on_cpu

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )
    def _embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self._model,
            "input": texts,
            "keep_alive": self._keep_alive,
        }
        if self._cpu:
            payload["options"] = {"num_gpu": 0}
        r = self._client.post("/api/embed", json=payload)
        r.raise_for_status()
        embeddings: list[list[float]] = r.json()["embeddings"]
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Se enviaron {len(texts)} textos pero Ollama devolvió {len(embeddings)} embeddings"
            )
        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            out.extend(self._embed(texts[i : i + self._batch]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def dimension(self) -> int:
        return len(self.embed_query("dimension probe"))
