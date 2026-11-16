"""Indexa el vault de EJEMPLO con Ollama y Qdrant reales y comprueba búsquedas de verdad."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer, SyncReport
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

pytestmark = pytest.mark.integration

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
IPTABLES = "4º/Seguridad/Cortafuegos con iptables.md"
REDES = "3º/REDES/Network layers.md"


@dataclass
class Stack:
    indexer: Indexer
    embedder: OllamaEmbedder
    store: VectorStore
    manifest: Manifest
    first: SyncReport

    def top(self, query: str, k: int = 3) -> list[str]:
        hits = self.store.search(query, self.embedder.embed_query(query), limit=k)
        return [str(h.payload["note_path"]) for h in hits]


@pytest.fixture(scope="module")
def stack(vault: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    tmp = tmp_path_factory.mktemp("e2e")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        vault_path=vault,
        collection=f"test_e2e_{uuid.uuid4().hex[:8]}",
        manifest_path=tmp / "manifest.sqlite",
        bm25_cache_dir=Path("data/fastembed_cache"),
        embed_on_cpu=True,
    )
    embedder = OllamaEmbedder(settings)
    store = VectorStore(settings, dim=embedder.dimension())
    store.ensure_collection()
    manifest = Manifest(settings.manifest_path)
    indexer = Indexer(settings, embedder, store, manifest)
    first = indexer.sync()
    yield Stack(indexer, embedder, store, manifest, first)
    store.delete_collection()
    manifest.close()


def test_first_sync_indexes_the_fixture_vault(stack: Stack) -> None:
    r = stack.first
    assert (r.indexed, r.empty, r.deleted, r.failed) == (9, 1, 0, [])
    assert stack.store.count() == stack.manifest.totals()[1]


def test_second_sync_is_idempotent(stack: Stack) -> None:
    r = stack.indexer.sync()
    assert (r.indexed, r.unchanged, r.failed) == (0, 10, [])


def test_exact_term_query_finds_iptables_note(stack: Stack) -> None:
    assert stack.top("iptables")[0] == IPTABLES


def test_semantic_spanish_query_finds_race_condition_note(stack: Stack) -> None:
    assert stack.top("cómo evitar condiciones de carrera entre hilos")[0] == CARRERA


def test_english_query_finds_english_note(stack: Stack) -> None:
    assert stack.top("how does TCP guarantee reliable delivery")[0] == REDES
