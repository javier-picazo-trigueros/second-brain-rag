from __future__ import annotations

import json
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from qdrant_client.http.exceptions import ResponseHandlingException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from secondbrain import __version__
from secondbrain.answer.context import BuiltContext
from secondbrain.answer.pipeline import (
    DoneEvent,
    ErrorEvent,
    Event,
    SourcesEvent,
    TokenEvent,
    confidence_label,
)
from secondbrain.api.health import HealthReport
from secondbrain.api.reindex import AlreadyRunning, ReindexManager, ReindexStatus
from secondbrain.api.schemas import (
    AskRequest,
    BacklinkOut,
    ChunkOut,
    ConceptOut,
    FacetsOut,
    FacetValueOut,
    HealthOut,
    NeighborOut,
    NeighborsOut,
    NoteHitOut,
    NoteOut,
    ReindexStatusOut,
    RelatedOut,
    SearchRequest,
    SearchResponse,
    StatsOut,
    SubjectOut,
)
from secondbrain.config import Settings
from secondbrain.ingest.parser import parse_note
from secondbrain.obsidian import obsidian_url
from secondbrain.retrieval.catalog import Catalog
from secondbrain.retrieval.faceted import FacetedSearch, Filters
from secondbrain.retrieval.graph import ConceptGraph
from secondbrain.retrieval.hybrid import NoteHit, RelatedNote, SearchResult
from secondbrain.store.manifest import Manifest

log = logging.getLogger(__name__)
_LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
_OLLAMA_DOWN = "Ollama no responde en {url}: arráncalo con `ollama serve`."
_QDRANT_DOWN = "Qdrant no responde en {url}: arráncalo con `.\\tasks.ps1 up`."


class Retriever(Protocol):
    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult: ...


class Pipeline(Protocol):
    def ask(self, question: str, k: int | None = None) -> Iterator[Event]: ...

    def plan(self, question: str, k: int | None = None) -> tuple[SearchResult, BuiltContext]: ...


@dataclass(slots=True)
class AppServices:
    settings: Settings
    retriever: Retriever
    pipeline: Pipeline
    manifest: Manifest
    health: Callable[[], HealthReport]
    reindex: ReindexManager
    points: Callable[[], int]  # chunks indexados en Qdrant
    warmup: Callable[[], None] | None = None  # precalienta embedder, BM25 y Qdrant al arrancar
    catalog: Catalog | None = None  # asignaturas canónicas y etiquetas (filtros y facetas)


def _title(path: str) -> str:
    return PurePosixPath(path).stem


def _note_hit(note: NoteHit, catalog: Catalog | None = None) -> NoteHitOut:
    first = note.chunks[0].payload if note.chunks else {}
    subject = catalog.subject_name(note.path) if catalog else None
    course = catalog.course(note.path) if catalog else None
    return NoteHitOut(
        path=note.path,
        title=note.title,
        score=note.score,
        raw_score=note.raw_score,
        n_chunks=note.n_chunks,
        asignatura=subject or first.get("asignatura"),
        curso=course or first.get("curso"),
        tags=list(first.get("tags") or []),
        also_in=list(note.also_in),
        chunks=[
            ChunkOut(
                heading_path=str(h.payload.get("heading_path", "")),
                page=h.payload.get("page"),
                text=str(h.payload.get("text", "")),
                score=h.score,
            )
            for h in note.chunks
        ],
    )


def _related(rel: RelatedNote) -> RelatedOut:
    return RelatedOut(
        path=rel.path,
        title=_title(rel.path),
        score=rel.score,
        via=list(rel.via),
        seeds=list(rel.seeds),
        resumen=rel.resumen,
        heading_path=rel.heading_path,
        page=rel.page,
        snippet=rel.snippet,
    )


def _sse(event: Event) -> str:
    name = {
        SourcesEvent: "sources",
        TokenEvent: "token",
        DoneEvent: "done",
        ErrorEvent: "error",
    }[type(event)]
    return f"event: {name}\ndata: {json.dumps(asdict(event), ensure_ascii=False)}\n\n"


def _sse_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"


# Rutas de la API y de los ficheros del build: si faltan, 404 (no la página de la aplicación).
_NOT_THE_APP = (
    "health",
    "stats",
    "search",
    "ask",
    "notes",
    "graph",
    "reindex",
    "docs",
    "redoc",
    "openapi.json",
    "assets",
)
# Un fichero estático que falta es un 404; el resto de rutas (también `/nota/…/x.md`) son de la app.

# Un fichero estático que falta es un 404; el resto de rutas (también `/nota/…/algo.md`) son de la app.
_STATIC_EXTENSIONS = frozenset(
    {"js", "mjs", "css", "map", "png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "avif",
     "woff", "woff2", "ttf", "otf", "json", "txt", "xml", "webmanifest", "wasm"}
)  # fmt: skip


def _serve_build(app: FastAPI, build: Path) -> None:
    """Sirve la interfaz compilada: ficheros del build tal cual y, para cualquier otra ruta del
    navegador (`/estado`...), `index.html` (el enrutador de la aplicación decide)."""
    root = build.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def interface(path: str) -> Response:
        target = (root / path).resolve() if path else index
        first = path.split("/", 1)[0]
        if path and target.is_file() and target.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if first == "assets" else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        extension = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        if first in _NOT_THE_APP or extension in _STATIC_EXTENSIONS:
            raise HTTPException(404, "No encontrado.")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def _run_warmup(warmup: Callable[[], None]) -> None:
    try:
        warmup()
    except (httpx.HTTPError, ResponseHandlingException) as exc:
        # Ollama o Qdrant aún no están: la primera pregunta cargará lo que falte.
        log.warning("No se pudo precalentar la búsqueda: %s", exc)


def create_app(services: AppServices, static_dir: Path | None = None) -> FastAPI:
    settings = services.settings
    manifest = services.manifest

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if services.warmup is not None:
            threading.Thread(target=_run_warmup, args=(services.warmup,), daemon=True).start()
        yield

    app = FastAPI(
        lifespan=lifespan,
        title="Segundo cerebro",
        version=__version__,
        description="RAG local sobre un vault de Obsidian. Solo escucha en localhost.",
    )
    # Defensa contra DNS rebinding: solo se atienden peticiones dirigidas a la propia máquina.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_LOCAL_HOSTS)
    if settings.api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(httpx.TransportError)
    async def _ollama_down(_: Request, __: httpx.TransportError) -> JSONResponse:
        return JSONResponse(
            {"detail": _OLLAMA_DOWN.format(url=settings.ollama_url)}, status_code=503
        )

    @app.exception_handler(ResponseHandlingException)
    async def _qdrant_down(_: Request, __: ResponseHandlingException) -> JSONResponse:
        return JSONResponse(
            {"detail": _QDRANT_DOWN.format(url=settings.qdrant_url)}, status_code=503
        )

    def indexed_path(path: str) -> str:
        clean = path.replace("\\", "/")
        if clean.startswith("/") or ".." in clean.split("/") or not clean.lower().endswith(".md"):
            raise HTTPException(400, "Ruta de nota no válida.")
        if manifest.get(clean) is None:
            raise HTTPException(404, "La nota no está en el índice.")
        return clean

    def neighbours(path: str, limit: int) -> list[NeighborOut]:
        graph = ConceptGraph.from_manifest(manifest)
        found = graph.expand(
            [(path, 1.0)],
            fanout_cap=settings.graph_fanout_cap,
            budget=limit,
            min_idf=settings.graph_min_idf,
        )
        return [
            NeighborOut(path=r.path, title=_title(r.path), score=r.score, via=list(r.via))
            for r in found
        ]

    @app.get("/health", response_model=HealthOut, tags=["estado"])
    def health() -> HealthOut:
        return HealthOut.model_validate(asdict(services.health()))

    @app.get("/stats", response_model=StatsOut, tags=["estado"])
    def stats() -> StatsOut:
        notes, chunks = manifest.totals()
        concepts = {c for cs in manifest.note_concepts().values() for c in cs}
        return StatsOut(
            notes=notes,
            chunks=chunks,
            points=services.points(),
            duplicate_groups=len(manifest.duplicate_groups()),
            concepts=len(concepts),
            last_sync=manifest.get_value("last_sync"),
        )

    @app.post("/search", response_model=SearchResponse, tags=["búsqueda"])
    def search(request: SearchRequest) -> SearchResponse:
        facets = FacetsOut()
        if services.catalog is None:
            result = services.retriever.search(request.query, k=request.k, with_graph=request.graph)
        else:
            filters = Filters(
                tuple(request.asignaturas), tuple(request.cursos), tuple(request.tags)
            )
            out = FacetedSearch(services.retriever, services.catalog).search(
                request.query, request.k, with_graph=request.graph, filters=filters
            )
            result = out.result
            facets = FacetsOut(
                asignaturas=[
                    FacetValueOut(value=f.value, count=f.count) for f in out.facets.asignaturas
                ],
                cursos=[FacetValueOut(value=f.value, count=f.count) for f in out.facets.cursos],
                tags=[FacetValueOut(value=f.value, count=f.count) for f in out.facets.tags],
            )
        return SearchResponse(
            facets=facets,
            notes=[_note_hit(n, services.catalog) for n in result.notes],
            related=[_related(r) for r in result.related],
            top_similarity=result.top_similarity,
            confidence=confidence_label(result.top_similarity, settings.confidence_threshold),
        )

    @app.get("/subjects", response_model=list[SubjectOut], tags=["búsqueda"])
    def subjects() -> list[SubjectOut]:
        if services.catalog is None:
            return []
        return [SubjectOut(name=n, notes=c) for n, c in services.catalog.subjects()]

    @app.post("/ask", tags=["búsqueda"], response_class=StreamingResponse)
    def ask(request: AskRequest) -> StreamingResponse:
        """Respuesta en streaming (Server-Sent Events): `sources`, `token`*, `done` o `error`."""

        def stream() -> Iterator[str]:
            try:
                for event in services.pipeline.ask(request.question, request.k):
                    yield _sse(event)
            except httpx.TransportError:
                yield _sse_error(_OLLAMA_DOWN.format(url=settings.ollama_url))
            except ResponseHandlingException:
                yield _sse_error(_QDRANT_DOWN.format(url=settings.qdrant_url))

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/notes/{path:path}", response_model=NoteOut, tags=["notas"])
    def note(path: str, related: int = Query(8, ge=0, le=50)) -> NoteOut:
        clean = indexed_path(path)
        try:
            parsed = parse_note(settings.vault_path / clean, settings.vault_path)
        except FileNotFoundError as exc:
            raise HTTPException(404, "La nota ya no existe en el vault.") from exc
        fm = parsed.frontmatter
        return NoteOut(
            path=parsed.path,
            title=parsed.title,
            asignatura=str(fm["asignatura"]) if fm.get("asignatura") is not None else None,
            curso=str(fm["curso"]) if fm.get("curso") is not None else None,
            frontmatter=jsonable_encoder(fm),
            tags=list(parsed.tags),
            concepts=list(parsed.concepts),
            links=list(parsed.links),
            body=parsed.body,
            related=neighbours(clean, related) if related else [],
            resolved_links=(
                {t: services.catalog.resolve_link(t, near=clean) for t in parsed.links}
                if services.catalog
                else {}
            ),
            backlinks=(
                [BacklinkOut(path=p, title=_title(p)) for p in services.catalog.backlinks(clean)]
                if services.catalog
                else []
            ),
            obsidian_url=obsidian_url(settings.obsidian_vault_name, clean),
        )

    @app.get("/graph/neighbors/{path:path}", response_model=NeighborsOut, tags=["notas"])
    def graph_neighbors(path: str, limit: int = Query(10, ge=1, le=50)) -> NeighborsOut:
        clean = indexed_path(path)
        graph = ConceptGraph.from_manifest(manifest)
        return NeighborsOut(
            path=clean,
            concepts=[
                ConceptOut(name=c, notes=len(graph.notes_of(c)), idf=graph.idf(c))
                for c in graph.concepts_of(clean)
            ],
            neighbors=neighbours(clean, limit),
        )

    @app.post("/reindex", response_model=ReindexStatusOut, status_code=202, tags=["índice"])
    def reindex() -> ReindexStatusOut:
        try:
            services.reindex.start()
        except AlreadyRunning as exc:
            raise HTTPException(409, "Ya hay un reindexado en marcha.") from exc
        return _reindex_status(services.reindex.status())

    @app.get("/reindex/status", response_model=ReindexStatusOut, tags=["índice"])
    def reindex_status() -> ReindexStatusOut:
        return _reindex_status(services.reindex.status())

    if static_dir is not None and (static_dir / "index.html").is_file():
        _serve_build(app, static_dir)
    return app


def _reindex_status(status: ReindexStatus) -> ReindexStatusOut:
    data: dict[str, Any] = asdict(status)
    report = data.pop("report")
    if report is not None:
        report["failed"] = [{"path": p, "error": e} for p, e in report["failed"]]
    return ReindexStatusOut.model_validate({**data, "report": report})
