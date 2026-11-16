from __future__ import annotations

from pathlib import Path

import httpx
import pytest

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"
OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = "http://127.0.0.1:6333"
EMBED_MODEL = "bge-m3"


@pytest.fixture(scope="session")
def vault() -> Path:
    """Vault de ejemplo. Los tests nunca tocan el vault real."""
    return FIXTURE_VAULT


def _services_problem() -> str | None:
    """Devuelve por qué no se pueden ejecutar los tests de integración, o None si se puede."""
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3).json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"Ollama no responde en {OLLAMA_URL} ({type(exc).__name__})"
    names = {m.get("name", "") for m in tags.get("models", [])}
    if not any(n.split(":")[0] == EMBED_MODEL for n in names):
        return f"falta el modelo: ollama pull {EMBED_MODEL}"
    try:
        httpx.get(f"{QDRANT_URL}/healthz", timeout=3).raise_for_status()
    except httpx.HTTPError as exc:
        return f"Qdrant no responde en {QDRANT_URL} ({type(exc).__name__}): .\\tasks.ps1 up"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    integration = [i for i in items if "integration" in i.keywords]
    if not integration:
        return
    problem = _services_problem()
    if problem is None:
        return
    skip = pytest.mark.skip(reason=f"integración: {problem}")
    for item in integration:
        item.add_marker(skip)
