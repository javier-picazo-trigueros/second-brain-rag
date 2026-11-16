from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Annotated, NoReturn

import httpx
import typer
import uvicorn
from pydantic import ValidationError
from qdrant_client.http.exceptions import ResponseHandlingException

from secondbrain.config import Settings, load_settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer, SyncReport
from secondbrain.ingest.watcher import WatcherService
from secondbrain.notes import resolve_note
from secondbrain.protocols import Embedder, Store
from secondbrain.retrieval.graph import ConceptGraph
from secondbrain.retrieval.hybrid import HybridRetriever, NoteHit, RelatedNote
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

app = typer.Typer(no_args_is_help=True, help="Segundo cerebro local (RAG sobre Obsidian)")

_EXIT_ENVIRONMENT = 2
_SNIPPET = 160


@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    embedder: Embedder
    store: Store
    manifest: Manifest


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(_EXIT_ENVIRONMENT)


def _settings() -> Settings:
    try:
        return load_settings()
    except ValidationError as exc:
        problems = "\n".join(
            f"  BRAIN_{'_'.join(str(p) for p in e['loc']).upper()}: {e['msg']}"
            for e in exc.errors()
        )
        _fail(
            f"Configuración inválida:\n{problems}\n"
            "Copia .env.example a .env y ajusta BRAIN_VAULT_PATH."
        )


def _build() -> Services:
    settings = _settings()

    embedder = OllamaEmbedder(settings)
    try:
        dim = embedder.dimension()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            _fail(
                f"Ollama no tiene el modelo '{settings.embed_model}': "
                f"ejecuta `ollama pull {settings.embed_model}`."
            )
        raise
    except httpx.TransportError:
        _fail(f"Ollama no responde en {settings.ollama_url}: arráncalo con `ollama serve`.")

    try:
        store = VectorStore(settings, dim=dim)
        store.ensure_collection()
    except ResponseHandlingException:
        _fail(f"Qdrant no responde en {settings.qdrant_url}: arráncalo con `.\\tasks.ps1 up`.")
    return Services(settings, embedder, store, Manifest(settings.manifest_path))


def _summary(report: SyncReport) -> str:
    return (
        f"indexadas={report.indexed} sin_cambios={report.unchanged} vacias={report.empty} "
        f"borradas={report.deleted} fallos={len(report.failed)}"
    )


@app.command()
def index() -> None:
    """Sincroniza el vault con el índice (solo notas nuevas, cambiadas o borradas)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    svc = _build()
    report = Indexer(svc.settings, svc.embedder, svc.store, svc.manifest).sync()
    typer.echo(_summary(report))
    for path, err in report.failed:
        typer.echo(f"  FALLO {path}: {err}", err=True)
    if report.failed:
        raise typer.Exit(1)


def _echo_note(position: int, note: NoteHit) -> None:
    first = note.chunks[0].payload
    page = f" (p. {first['page']})" if first.get("page") is not None else ""
    snippet = str(first["text"]).replace("\n", " ")[:_SNIPPET]
    typer.echo(f"{position:>2}. {note.score:.3f}  {note.path}  [{first['heading_path']}]{page}")
    typer.echo(f"      {snippet}")
    if note.also_in:
        typer.echo(f"      también en: {', '.join(note.also_in)}")


def _echo_related(rel: RelatedNote) -> None:
    typer.echo(f"  - {rel.path}  (vía: {', '.join(rel.via)})")
    detail = rel.resumen or rel.snippet
    if detail:
        typer.echo(f"      {detail.replace(chr(10), ' ')[:_SNIPPET]}")


@app.command()
def search(
    query: str,
    k: Annotated[int, typer.Option("--k", "-k", help="Número de notas.")] = 5,
    graph: Annotated[
        bool, typer.Option("--graph/--no-graph", help="Notas relacionadas por el grafo.")
    ] = True,
) -> None:
    """Búsqueda híbrida (vectorial + BM25), una entrada por nota, y relacionadas por el grafo."""
    svc = _build()
    retriever = HybridRetriever(svc.settings, svc.embedder, svc.store, svc.manifest)
    result = retriever.search(query, k=k, with_graph=graph)
    if not result.notes:
        typer.echo("Sin resultados.")
        return
    for position, note in enumerate(result.notes, start=1):
        _echo_note(position, note)
    if result.related:
        typer.echo("\nRelacionadas por el grafo:")
        for rel in result.related:
            _echo_related(rel)


@app.command()
def graph(
    note: Annotated[str, typer.Argument(help="Ruta relativa o título de la nota.")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Vecinas a mostrar.")] = 10,
) -> None:
    """Conceptos de una nota y las notas con las que se conecta en el grafo."""
    svc = _build()
    note_concepts = svc.manifest.note_concepts()
    matches = resolve_note(note_concepts, note)
    if not matches:
        typer.echo(f"No encuentro ninguna nota «{note}» en el índice.", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo(f"«{note}» es ambiguo, indica la ruta completa:", err=True)
        for path in matches:
            typer.echo(f"  {path}", err=True)
        raise typer.Exit(1)
    path = matches[0]
    g = ConceptGraph(note_concepts)
    typer.echo(f"Nota: {path}")
    typer.echo(f"Conceptos: {', '.join(g.concepts_of(path)) or '(ninguno)'}")
    related = g.expand(
        [(path, 1.0)],
        fanout_cap=svc.settings.graph_fanout_cap,
        budget=limit,
        min_idf=svc.settings.graph_min_idf,
    )
    typer.echo("Relacionadas:" if related else "Sin notas relacionadas.")
    for rel in related:
        typer.echo(f"  {rel.score:.3f}  {rel.path}  (vía: {', '.join(rel.via)})")


@app.command()
def watch() -> None:
    """Sincroniza el índice y lo mantiene al día mientras editas el vault (Ctrl+C para salir)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    svc = _build()
    if not svc.settings.embed_on_cpu:
        typer.echo(
            "Consejo: con BRAIN_EMBED_ON_CPU=true el embedder no compite con el LLM por la VRAM.",
            err=True,
        )
    indexer = Indexer(svc.settings, svc.embedder, svc.store, svc.manifest)
    typer.echo(_summary(indexer.sync()))
    service = WatcherService(indexer, svc.settings)
    typer.echo(f"Vigilando {svc.settings.vault_path} ...")
    stop = threading.Event()
    try:
        service.run(stop)
    except KeyboardInterrupt:
        stop.set()
        typer.echo("Detenido.")


@app.command()
def stats() -> None:
    """Notas, chunks, copias exactas y conceptos del índice."""
    svc = _build()
    notes, chunks = svc.manifest.totals()
    concepts = {c for cs in svc.manifest.note_concepts().values() for c in cs}
    typer.echo(
        f"notas={notes} chunks_manifest={chunks} puntos_qdrant={svc.store.count()} "
        f"grupos_de_copias={len(svc.manifest.duplicate_groups())} conceptos={len(concepts)}"
    )


_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


@app.command()
def serve(
    host: Annotated[
        str | None, typer.Option(help="Dirección (por defecto BRAIN_API_HOST).")
    ] = None,
    port: Annotated[int | None, typer.Option(help="Puerto (por defecto BRAIN_API_PORT).")] = None,
    allow_remote: Annotated[
        bool, typer.Option("--allow-remote", help="Permite escuchar fuera de esta máquina.")
    ] = False,
) -> None:
    """Arranca la API HTTP (solo en localhost salvo que se pida otra cosa)."""
    settings = _settings()
    bind = host or settings.api_host
    if bind not in _LOOPBACK:
        if not allow_remote:
            _fail(
                f"Escuchar en {bind} expondría tus apuntes a la red y la API no tiene "
                "autenticación. Si es lo que quieres, añade --allow-remote."
            )
        typer.echo(f"AVISO: escuchando en {bind} sin autenticación.", err=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(
        "secondbrain.api.main:create_app_from_env",
        factory=True,
        host=bind,
        port=port or settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    app()
