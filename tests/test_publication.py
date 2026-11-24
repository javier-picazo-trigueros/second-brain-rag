"""Publicación con cliente en memoria, vectores dispersos simulados y dos lectores de SQLite."""

from concurrent.futures import ThreadPoolExecutor, wait
from threading import Event
from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest
from qdrant_client import QdrantClient

from secondbrain.domain import Chunk
from secondbrain.ingest.indexer import Indexer
from secondbrain.store.qdrant import VectorStore
from tests.env import Env


@pytest.mark.parametrize("legacy", [True, False])
@pytest.mark.parametrize("failure", ["bm25", "upsert", "cleanup", "reader", "none"])
def test_search_sees_one_complete_generation(
    env: Env, monkeypatch: pytest.MonkeyPatch, failure: str, legacy: bool
) -> None:
    client = QdrantClient(":memory:")
    monkeypatch.setattr("secondbrain.store.qdrant.QdrantClient", lambda **kw: client)
    sparse = Mock()
    vector = Mock(indices=np.array([1]), values=np.array([1.0]))
    sparse.embed.side_effect = lambda texts: [vector for _ in texts]
    sparse.query_embed.return_value = [vector]
    monkeypatch.setattr("secondbrain.store.qdrant.SparseTextEmbedding", lambda **kw: sparse)
    monkeypatch.setattr("secondbrain.store.qdrant._UPSERT_BATCH", 1)
    s = env.settings(chunk_max_chars=500, chunk_min_chars=100, bm25_cache_dir=env.tmp / "cache")
    store = VectorStore(s, dim=3)
    store.ensure_collection()
    reader = VectorStore(s)
    idx = Indexer(s, env.embedder, store, env.manifest)
    path = "A.md"
    env.write(path, "# Antes\n\n" + "material anterior. " * 90)
    if legacy:
        from secondbrain.ingest.chunker import chunk_note
        from secondbrain.ingest.parser import parse_note

        parsed = parse_note(env.vault / path, env.vault)
        chunks = chunk_note(parsed, s.chunk_max_chars, s.chunk_min_chars)
        store.upsert_chunks(chunks, env.embedder.embed_documents([c.embed_text for c in chunks]))
        env.manifest.upsert(path, "legacy", len(chunks))
    else:
        idx.index_file(env.vault / path)

    def results() -> list[str]:
        return sorted(h.payload["text"] for h in reader.search("material", [1, 0, 0], limit=50))

    old = results()
    assert len(old) > 1
    env.write(path, "# Ahora\n\n" + "material nuevo. " * 80)
    upsert = client.upsert
    snapshots = []

    def staged(*args: Any, **kwargs: Any) -> Any:
        result = upsert(*args, **kwargs)
        snapshots.append(results())
        if failure == "upsert":
            raise RuntimeError("upsert")
        return result

    monkeypatch.setattr(client, "upsert", staged)
    if failure == "bm25":
        sparse.embed.side_effect = RuntimeError("bm25")
    retire = store.retire_versions
    published: list[list[str]] = []

    def before_retire(note_path: str, keep: str) -> None:
        published.append(results())
        assert client.count(s.collection, exact=True).count > len(published[-1])
        if failure == "cleanup" and len(published) == 1:
            raise RuntimeError("cleanup")
        retire(note_path, keep)

    monkeypatch.setattr(store, "retire_versions", before_retire)
    if failure == "reader":
        # Detener la primera búsqueda después de escoger versión y antes de consultar puntos.
        selected, staged_points = Event(), Event()
        query_points = client.query_points

        def delayed(*args: Any, **kwargs: Any) -> Any:
            if not selected.is_set():
                selected.set()
                assert staged_points.wait(5)
                wait([writer], timeout=0.3)
            return query_points(*args, **kwargs)

        def writer_task() -> None:
            assert selected.wait(5)
            idx.index_file(env.vault / path)

        def signal_stage(chunks: list[Chunk], vectors: list[list[float]]) -> None:
            original_stage(chunks, vectors)
            staged_points.set()

        original_stage = store.upsert_chunks
        monkeypatch.setattr(store, "upsert_chunks", signal_stage)
        monkeypatch.setattr(client, "query_points", delayed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            writer = pool.submit(writer_task)
            assert results() == old
            writer.result()
    elif failure != "none":
        with pytest.raises(RuntimeError, match=failure):
            idx.index_file(env.vault / path)
        assert results() == (published[0] if failure == "cleanup" else old)
        sparse.embed.side_effect = lambda texts: [vector for _ in texts]
        monkeypatch.setattr(client, "upsert", upsert)
    idx.index_file(env.vault / path)
    assert all(snapshot == old for snapshot in snapshots)
    if failure != "bm25":
        assert snapshots
    final = results()
    assert published and all(snapshot == final for snapshot in published)
    assert client.count(s.collection, exact=True).count == len(final)
    assert final and all("nuevo" in text for text in final)
    assert len(final) == env.manifest.chunk_counts()[path] == store.count()


def test_the_qdrant_client_gets_a_patient_timeout_from_the_settings(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bajo carga, crear índices o publicar puede tardar más que el plazo por defecto (5 s)."""
    seen: dict[str, Any] = {}

    def fake_client(**kwargs: Any) -> QdrantClient:
        seen.update(kwargs)
        return QdrantClient(":memory:")

    monkeypatch.setattr("secondbrain.store.qdrant.QdrantClient", fake_client)
    monkeypatch.setattr("secondbrain.store.qdrant.SparseTextEmbedding", lambda **kw: Mock())
    s = env.settings(bm25_cache_dir=env.tmp / "cache", qdrant_timeout_s=45)
    VectorStore(s, dim=3)
    assert seen["timeout"] == 45
    assert env.settings().qdrant_timeout_s == 30  # por defecto, holgado
