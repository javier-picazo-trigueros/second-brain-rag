from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from secondbrain.config import Settings
from secondbrain.domain import Chunk, Hit
from secondbrain.net import use_system_trust_store
from secondbrain.store.manifest import Manifest

DENSE = "dense"
SPARSE = "bm25"
_UPSERT_BATCH = 64
_KEYWORD_INDEXES = ("note_path", "generation", "tags", "asignatura", "curso")


class VectorStore:
    def __init__(self, settings: Settings, dim: int | None = None) -> None:
        self._client = QdrantClient(url=settings.qdrant_url, timeout=int(settings.qdrant_timeout_s))
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
        self._manifest_path = settings.manifest_path

    @property
    def collection_name(self) -> str:
        return self._name

    def ensure_collection(self) -> None:
        if self._dim is None:
            raise RuntimeError(
                "No se conoce la dimensión de los embeddings: este VectorStore es de solo lectura."
            )
        if self._client.collection_exists(self._name):
            info = self._client.get_collection(self._name)
            vectors = info.config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) else None
            if size != self._dim:
                raise RuntimeError(
                    f"La colección usa dim={size} pero el embedder da {self._dim}. "
                    "Cambiaste de modelo: borra la colección y el manifest y reindexa."
                )
            # Colecciones anteriores al versionado: crear los índices que falten.
            self._create_missing_indexes(set(info.payload_schema))
            return
        self._client.create_collection(
            self._name,
            vectors_config={
                DENSE: models.VectorParams(size=self._dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        self._create_missing_indexes(set())

    def _create_missing_indexes(self, existing: set[str]) -> None:
        for field in _KEYWORD_INDEXES:
            if field not in existing:
                self._client.create_payload_index(
                    self._name, field_name=field, field_schema=models.PayloadSchemaType.KEYWORD
                )

    def delete_collection(self) -> None:
        self._client.delete_collection(self._name)

    @staticmethod
    def _payload(c: Chunk) -> dict[str, object]:
        return {
            "generation": c.generation,
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

    def retire_versions(self, note_path: str, keep: str) -> None:
        self._client.delete(
            self._name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(key="note_path", match=models.MatchValue(value=note_path))
                ],
                must_not=[
                    models.FieldCondition(key="generation", match=models.MatchValue(value=keep))
                ],
            ),
            wait=True,
        )

    def update_links(self, note_path: str, links: Sequence[str]) -> None:
        """Reescribe solo el payload `links` de todos los puntos de la nota (sin vectores)."""
        self._client.set_payload(
            self._name,
            payload={"links": list(links)},
            points=models.Filter(
                must=[
                    models.FieldCondition(key="note_path", match=models.MatchValue(value=note_path))
                ]
            ),
            wait=True,
        )

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

    @contextmanager
    def _visible(self, only_paths: Sequence[str] | None = None) -> Iterator[models.Filter]:
        with Manifest.read_generations(self._manifest_path) as versions:
            yield self._paths_filter(versions, only_paths)

    @staticmethod
    def _paths_filter(versions: dict[str, str], only_paths: Sequence[str] | None) -> models.Filter:
        if only_paths is not None:
            versions = {p: versions[p] for p in only_paths if p in versions}

        # Los índices anteriores a la migración carecen de generación. Se admiten sus
        # puntos solo hasta la primera publicación versionada de la misma ruta.
        legacy = models.Filter(
            must=[models.IsEmptyCondition(is_empty=models.PayloadField(key="generation"))],
            must_not=[
                models.FieldCondition(key="note_path", match=models.MatchAny(any=list(versions)))
            ],
        )
        visible = models.Filter(
            should=[
                legacy,
                models.FieldCondition(
                    key="generation", match=models.MatchAny(any=list(versions.values()))
                ),
            ]
        )
        if only_paths is None:
            return visible
        return models.Filter(
            must=[
                visible,
                models.FieldCondition(key="note_path", match=models.MatchAny(any=list(only_paths))),
            ]
        )

    def search(
        self,
        query: str,
        query_dense: list[float],
        limit: int = 8,
        prefetch: int = 40,
        only_paths: Sequence[str] | None = None,
    ) -> list[Hit]:
        s = next(iter(self._sparse.query_embed(query)))
        with self._visible(only_paths) as within:
            res = self._client.query_points(
                self._name,
                prefetch=[
                    models.Prefetch(query=query_dense, using=DENSE, limit=prefetch, filter=within),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=s.indices.tolist(), values=s.values.tolist()
                        ),
                        using=SPARSE,
                        limit=prefetch,
                        filter=within,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
            return [Hit(score=p.score, payload=dict(p.payload or {})) for p in res.points]

    def search_note(self, note_path: str, query_dense: list[float], limit: int = 1) -> list[Hit]:
        """Los chunks de una nota más cercanos a la consulta (solo ranking denso)."""
        with self._visible([note_path]) as within:
            res = self._client.query_points(
                self._name,
                query=query_dense,
                using=DENSE,
                query_filter=within,
                limit=limit,
                with_payload=True,
            )
            return [Hit(score=p.score, payload=dict(p.payload or {})) for p in res.points]

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        """Etiquetas de cada nota (las del frontmatter, repetidas en sus chunks), sin vectores."""
        out: dict[str, tuple[str, ...]] = {}
        with self._visible() as within:
            offset = None
            while True:
                points, offset = self._client.scroll(
                    self._name,
                    scroll_filter=within,
                    limit=1000,
                    offset=offset,
                    with_payload=["note_path", "tags"],
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    out.setdefault(
                        str(payload["note_path"]), tuple(str(t) for t in payload.get("tags") or [])
                    )
                if offset is None:
                    return out

    def note_links(self) -> dict[str, tuple[str, ...]]:
        """Destinos de los `[[enlaces]]` de cada nota (los del cuerpo y del frontmatter)."""
        out: dict[str, tuple[str, ...]] = {}
        with self._visible() as within:
            offset = None
            while True:
                points, offset = self._client.scroll(
                    self._name,
                    scroll_filter=within,
                    limit=1000,
                    offset=offset,
                    with_payload=["note_path", "links"],
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    links = tuple(str(t) for t in payload.get("links") or [])
                    out.setdefault(str(payload["note_path"]), links)
                if offset is None:
                    return out

    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        """Resumen, posición y encabezado de todos los chunks de esas notas (sin vectores)."""
        out: list[dict[str, Any]] = []
        with self._visible(paths) as within:
            offset = None
            while True:
                points, offset = self._client.scroll(
                    self._name,
                    scroll_filter=within,
                    limit=1000,
                    offset=offset,
                    with_payload=["note_path", "position", "heading_path", "resumen"],
                    with_vectors=False,
                )
                out.extend(dict(p.payload or {}) for p in points)
                if offset is None:
                    return out

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]:
        """Todos los chunks de esas notas con su texto, por nota y en orden de posición."""
        out: list[dict[str, Any]] = []
        with self._visible(paths) as within:
            offset = None
            while True:
                points, offset = self._client.scroll(
                    self._name,
                    scroll_filter=within,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                out.extend(dict(p.payload or {}) for p in points)
                if offset is None:
                    break
            order = {p: i for i, p in enumerate(paths)}
            return sorted(
                out, key=lambda c: (order.get(str(c["note_path"]), len(order)), int(c["position"]))
            )

    def dense_notes(
        self, query_dense: list[float], limit: int = 100, only_paths: Sequence[str] | None = None
    ) -> dict[str, float]:
        """Mejor coseno de cada nota entre los `limit` chunks más cercanos (solo ranking denso)."""
        with self._visible(only_paths) as within:
            res = self._client.query_points(
                self._name,
                query=query_dense,
                using=DENSE,
                query_filter=within,
                limit=limit,
                with_payload=["note_path"],
            )
            best: dict[str, float] = {}
            for point in res.points:
                best.setdefault(str((point.payload or {})["note_path"]), point.score)
            return best

    def dense_top(self, query_dense: list[float]) -> float | None:
        """Coseno del chunk más cercano a la consulta (solo ranking denso), o None si no hay."""
        with self._visible() as within:
            res = self._client.query_points(
                self._name,
                query=query_dense,
                using=DENSE,
                query_filter=within,
                limit=1,
                with_payload=False,
            )
            return res.points[0].score if res.points else None

    def count(self) -> int:
        with self._visible() as within:
            return self._client.count(self._name, count_filter=within, exact=True).count
