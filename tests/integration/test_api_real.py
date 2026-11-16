"""La API completa con Ollama y Qdrant reales, sobre el vault de EJEMPLO (nunca el real)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.main import create_app_from_env
from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

pytestmark = pytest.mark.integration

IPTABLES = "4º/Seguridad/Cortafuegos con iptables.md"


@pytest.fixture(scope="module")
def client(vault: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    tmp = tmp_path_factory.mktemp("api")
    env = {
        "BRAIN_VAULT_PATH": str(vault),
        "BRAIN_COLLECTION": f"test_api_{uuid.uuid4().hex[:8]}",
        "BRAIN_MANIFEST_PATH": str(tmp / "manifest.sqlite"),
        "BRAIN_ENV_FILE": str(tmp / "no-existe.env"),
    }
    patch = pytest.MonkeyPatch()
    for key, value in env.items():
        patch.setenv(key, value)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    embedder = OllamaEmbedder(settings.model_copy(update={"embed_on_cpu": True}))
    store = VectorStore(settings, dim=embedder.dimension())
    store.ensure_collection()
    manifest = Manifest(settings.manifest_path)
    Indexer(settings.model_copy(update={"embed_on_cpu": True}), embedder, store, manifest).sync()
    manifest.close()
    try:
        yield TestClient(create_app_from_env(), base_url="http://localhost")
    finally:
        store.delete_collection()
        patch.undo()


def events(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(ln[7:] for ln in lines if ln.startswith("event: "))
        out.append((name, json.loads(next(ln[6:] for ln in lines if ln.startswith("data: ")))))
    return out


def test_health_is_ok_with_the_real_services(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok", body["hints"]
    assert body["qdrant"]["points"] > 0


def test_stats_match_the_indexed_vault(client: TestClient) -> None:
    body = client.get("/stats").json()
    assert body["notes"] == 10 and body["chunks"] == body["points"] and body["last_sync"]


def test_search_finds_the_exact_term(client: TestClient) -> None:
    body = client.post("/search", json={"query": "iptables"}).json()
    assert body["notes"][0]["path"] == IPTABLES
    assert body["confidence"] in {"alta", "baja"}


def test_a_note_can_be_read_with_its_neighbours(client: TestClient) -> None:
    body = client.get(f"/notes/{IPTABLES}").json()
    assert body["title"] == "Cortafuegos con iptables" and "DROP" in body["body"]


def test_ask_answers_with_verified_citations_using_the_real_model(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "¿Qué política por defecto se usa en iptables?"})
    parsed = events(response.text)
    names = [n for n, _ in parsed]
    assert names[0] == "sources" and names[-1] == "done", parsed[-1]
    done = parsed[-1][1]
    source_paths = {s["path"] for s in parsed[0][1]["sources"]}
    assert done["answer"].strip()
    assert done["invalid"] == []
    assert done["citations"], done["warnings"]
    assert {c["path"] for c in done["citations"]} <= source_paths
    assert IPTABLES in {c["path"] for c in done["citations"]}
