"""Store de Qdrant contra un Qdrant real; cada test usa su propia colección y la borra."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from secondbrain.config import Settings
from secondbrain.domain import Chunk
from secondbrain.store.qdrant import VectorStore

pytestmark = pytest.mark.integration

DIM = 4
CACHE = Path("data/fastembed_cache")


def _chunk(path: str, text: str, pos: int = 0, page: int | None = None) -> Chunk:
    return Chunk(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path}#{pos}")),
        note_path=path,
        note_title=Path(path).stem,
        heading_path=("Tema", "Subtema"),
        text=text,
        position=pos,
        tags=("redes",),
        links=("otra",),
        asignatura="REDES",
        curso="3º",
        resumen="Resumen",
        page=page,
    )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[VectorStore]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        vault_path=tmp_path,
        collection=f"test_{uuid.uuid4().hex[:10]}",
        bm25_cache_dir=CACHE,
    )
    s = VectorStore(settings, dim=DIM)
    s.ensure_collection()
    yield s
    s.delete_collection()


def test_ensure_collection_is_idempotent(store: VectorStore) -> None:
    store.ensure_collection()
    assert store.count() == 0


def test_dimension_mismatch_is_reported(store: VectorStore, tmp_path: Path) -> None:
    other = Settings(  # type: ignore[call-arg]
        _env_file=None,
        vault_path=tmp_path,
        collection=store.collection_name,
        bm25_cache_dir=CACHE,
    )
    with pytest.raises(RuntimeError, match=r"dim=4.*8"):
        VectorStore(other, dim=8).ensure_collection()


def test_upsert_and_count(store: VectorStore) -> None:
    chunks = [_chunk("a.md", "uno dos tres", 0), _chunk("a.md", "cuatro cinco", 1)]
    store.upsert_chunks(chunks, [[1, 0, 0, 0], [0, 1, 0, 0]])
    assert store.count() == 2


def test_upsert_same_ids_replaces_instead_of_duplicating(store: VectorStore) -> None:
    chunk = _chunk("a.md", "uno dos tres")
    store.upsert_chunks([chunk], [[1, 0, 0, 0]])
    store.upsert_chunks([chunk], [[1, 0, 0, 0]])
    assert store.count() == 1


def test_delete_note_removes_only_that_note(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("a.md", "texto de a"), _chunk("b.md", "texto de b")],
        [[1, 0, 0, 0], [0, 1, 0, 0]],
    )
    store.delete_note("a.md")
    assert store.count() == 1
    hits = store.search("texto", [0, 1, 0, 0], limit=5)
    assert {h.payload["note_path"] for h in hits} == {"b.md"}


def test_payload_carries_metadata_and_page(store: VectorStore) -> None:
    store.upsert_chunks([_chunk("a.md", "contenido de prueba", page=7)], [[1, 0, 0, 0]])
    (hit,) = store.search("contenido", [1, 0, 0, 0], limit=1)
    p = hit.payload
    assert p["note_path"] == "a.md"
    assert p["note_title"] == "a"
    assert p["heading_path"] == "Tema > Subtema"
    assert p["page"] == 7
    assert (p["asignatura"], p["curso"], p["tags"]) == ("REDES", "3º", ["redes"])


def test_exact_term_is_found_by_bm25_even_if_dense_is_uninformative(store: VectorStore) -> None:
    same = [1.0, 0.0, 0.0, 0.0]
    store.upsert_chunks(
        [
            _chunk("seg.md", "Reglas de iptables para filtrar paquetes en Linux"),
            _chunk("ia.md", "La regresión lineal minimiza el error cuadrático"),
            _chunk("so.md", "Un semáforo protege la sección crítica de los hilos"),
        ],
        [same, same, same],
    )
    hits = store.search("iptables", same, limit=3)
    assert hits[0].payload["note_path"] == "seg.md"


def test_dense_vector_drives_semantic_match(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("x.md", "alfa beta"), _chunk("y.md", "gamma delta")],
        [[1, 0, 0, 0], [0, 1, 0, 0]],
    )
    hits = store.search("palabra inexistente", [0, 1, 0, 0], limit=2)
    assert hits[0].payload["note_path"] == "y.md"


def test_search_on_empty_collection_returns_nothing(store: VectorStore) -> None:
    assert store.search("lo que sea", [1, 0, 0, 0]) == []


def test_search_respects_limit(store: VectorStore) -> None:
    chunks = [_chunk(f"n{i}.md", f"texto numero {i}") for i in range(5)]
    store.upsert_chunks(chunks, [[1, 0, 0, 0]] * 5)
    assert len(store.search("texto", [1, 0, 0, 0], limit=3)) == 3


def test_search_note_returns_the_best_chunk_of_that_note_only(store: VectorStore) -> None:
    store.upsert_chunks(
        [
            _chunk("a.md", "poco relacionado", 0),
            _chunk("a.md", "muy relacionado", 1),
            _chunk("b.md", "idéntico a la consulta", 0),
        ],
        [[0, 1, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )
    (hit,) = store.search_note("a.md", [1, 0, 0, 0], limit=1)
    assert hit.payload["note_path"] == "a.md"
    assert hit.payload["text"] == "muy relacionado"


def test_search_note_of_unknown_note_is_empty(store: VectorStore) -> None:
    assert store.search_note("no-existe.md", [1, 0, 0, 0]) == []


def test_dense_top_returns_the_cosine_of_the_closest_chunk(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("a.md", "uno"), _chunk("b.md", "dos")], [[1, 0, 0, 0], [0, 1, 0, 0]]
    )
    assert store.dense_top([1, 0, 0, 0]) == pytest.approx(1.0)
    assert store.dense_top([1, 1, 0, 0]) == pytest.approx(0.7071, abs=1e-3)


def test_dense_top_of_an_empty_collection_is_none(store: VectorStore) -> None:
    assert store.dense_top([1, 0, 0, 0]) is None


def test_a_read_only_store_does_not_need_the_embedding_dimension(
    store: VectorStore, tmp_path: Path
) -> None:
    store.upsert_chunks([_chunk("a.md", "contenido de prueba")], [[1, 0, 0, 0]])
    reader = VectorStore(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            vault_path=tmp_path,
            collection=store.collection_name,
            bm25_cache_dir=CACHE,
        ),
        dim=None,
    )
    assert reader.count() == 1
    assert reader.search("contenido", [1, 0, 0, 0], limit=1)[0].payload["note_path"] == "a.md"
    with pytest.raises(RuntimeError, match="dimensión"):
        reader.ensure_collection()


def test_dense_notes_gives_the_best_cosine_per_note(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("a.md", "uno", 0), _chunk("a.md", "dos", 1), _chunk("b.md", "tres")],
        [[1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0]],
    )
    notes = store.dense_notes([1, 0, 0, 0])
    assert list(notes) == ["a.md", "b.md"]  # ordenadas de más a menos parecida
    assert notes["a.md"] == pytest.approx(1.0)
    assert notes["b.md"] == pytest.approx(0.0, abs=1e-6)


def test_only_paths_restricts_search_and_dense_notes(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("a.md", "semáforo"), _chunk("b.md", "semáforo")], [[1, 0, 0, 0], [1, 0, 0, 0]]
    )
    hits = store.search("semáforo", [1, 0, 0, 0], limit=10, prefetch=10, only_paths=["b.md"])
    assert {h.payload["note_path"] for h in hits} == {"b.md"}
    assert list(store.dense_notes([1, 0, 0, 0], only_paths=["b.md"])) == ["b.md"]


def test_note_tags_gives_the_tags_of_every_note_once(store: VectorStore) -> None:
    store.upsert_chunks(
        [_chunk("a.md", "uno", 0), _chunk("a.md", "dos", 1), _chunk("b.md", "tres")],
        [[1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0]],
    )
    assert store.note_tags() == {"a.md": ("redes",), "b.md": ("redes",)}
