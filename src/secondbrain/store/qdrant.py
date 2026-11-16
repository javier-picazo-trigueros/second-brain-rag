from __future__ import annotations

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from secondbrain.config import Settings
from secondbrain.domain import Chunk, Hit
from secondbrain.net import use_system_trust_store

DENSE = "dense"
SPARSE = "bm25"
_UPSERT_BATCH = 64
_KEYWORD_INDEXES = ("note_path", "tags", "asignatura", "curso")


class VectorStore:
    def __init__(self, settings: Settings, dim: int) -> None:
        self._client = QdrantClient(url=settings.qdrant_url)
        settings.bm25_cache_dir.mkdir(parents=True, exist_ok=True)
        use_system_trust_store()  # antivirus que inspecciona HTTPS: ver secondbrain.net
        # Primera ejecución: descarga única del modelo BM25. Después funciona sin conexión.
        self._sparse = SparseTextEmbedding(
            model_name="Qdrant/bm25",
            cache_dir=str(settings.bm25_cache_dir),
            language=settings.bm25_language,
        )
        self._name = settings.collection
        self._dim = dim

    @property
    def collection_name(self) -> str:
        return self._name

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self._name):
            vectors = self._client.get_collection(self._name).config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) else None
            if size != self._dim:
                raise RuntimeError(
                    f"La colección usa dim={size} pero el embedder da {self._dim}. "
                    "Cambiaste de modelo: borra la colección y el manifest y reindexa."
                )
            return
        self._client.create_collection(
            self._name,
            vectors_config={
                DENSE: models.VectorParams(size=self._dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field in _KEYWORD_INDEXES:
            self._client.create_payload_index(
                self._name, field_name=field, field_schema=models.PayloadSchemaType.KEYWORD
            )

    def delete_collection(self) -> None:
        self._client.delete_collection(self._name)

    @staticmethod
    def _payload(c: Chunk) -> dict[str, object]:
        return {
            "note_path": c.note_path,
            "note_title": c.note_title,
            "heading_path": " > ".join(c.heading_path),
            "position": c.position,
            "page": c.page,
            "text": c.text,
            "tags": list(c.tags),
            "links": list(c.links),
            "asignatura": c.asignatura,
            "curso": c.curso,
            "resumen": c.resumen,
        }

    def upsert_chunks(self, chunks: list[Chunk], dense: list[list[float]]) -> None:
        sparse = list(self._sparse.embed([c.embed_text for c in chunks]))
        points = [
            models.PointStruct(
                id=c.id,
                vector={
                    DENSE: d,
                    SPARSE: models.SparseVector(
                        indices=s.indices.tolist(), values=s.values.tolist()
                    ),
                },
                payload=self._payload(c),
            )
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        for i in range(0, len(points), _UPSERT_BATCH):
            self._client.upsert(self._name, points=points[i : i + _UPSERT_BATCH], wait=True)

    def delete_note(self, note_path: str) -> None:
        self._client.delete(
            self._name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="note_path", match=models.MatchValue(value=note_path)
                        )
                    ]
                )
            ),
            wait=True,
        )

    def search(
        self, query: str, query_dense: list[float], limit: int = 8, prefetch: int = 40
    ) -> list[Hit]:
        s = next(iter(self._sparse.query_embed(query)))
        res = self._client.query_points(
            self._name,
            prefetch=[
                models.Prefetch(query=query_dense, using=DENSE, limit=prefetch),
                models.Prefetch(
                    query=models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
                    using=SPARSE,
                    limit=prefetch,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [Hit(score=p.score, payload=dict(p.payload or {})) for p in res.points]

    def count(self) -> int:
        return self._client.count(self._name, exact=True).count
