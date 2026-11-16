from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, NoReturn

import httpx
import typer
from pydantic import ValidationError
from qdrant_client.http.exceptions import ResponseHandlingException

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer
from secondbrain.protocols import Embedder, Store
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

app = typer.Typer(no_args_is_help=True, help="Segundo cerebro local (RAG sobre Obsidian)")

_EXIT_ENVIRONMENT = 2


@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    embedder: Embedder
    store: Store
    manifest: Manifest


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(_EXIT_ENVIRONMENT)


def _build() -> Services:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = "\n".join(
            f"  BRAIN_{'_'.join(str(p) for p in e['loc']).upper()}: {e['msg']}"
            for e in exc.errors()
        )
        _fail(
            f"Configuración inválida:\n{problems}\n"
            "Copia .env.example a .env y ajusta BRAIN_VAULT_PATH."
        )

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


@app.command()
def index() -> None:
    """Sincroniza el vault con el índice (solo notas nuevas, cambiadas o borradas)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    svc = _build()
    report = Indexer(svc.settings, svc.embedder, svc.store, svc.manifest).sync()
    typer.echo(
        f"indexadas={report.indexed} sin_cambios={report.unchanged} vacias={report.empty} "
        f"borradas={report.deleted} fallos={len(report.failed)}"
    )
    for path, err in report.failed:
        typer.echo(f"  FALLO {path}: {err}", err=True)
    if report.failed:
        raise typer.Exit(1)


@app.command()
def search(
    query: str,
    k: Annotated[int, typer.Option("--k", "-k", help="Número de resultados.")] = 5,
) -> None:
    """Búsqueda híbrida (vectorial + BM25, fusión RRF)."""
    svc = _build()
    hits = svc.store.search(query, svc.embedder.embed_query(query), limit=k)
    if not hits:
        typer.echo("Sin resultados.")
        return
    for h in hits:
        p = h.payload
        page = f" (p. {p['page']})" if p.get("page") is not None else ""
        snippet = str(p["text"]).replace("\n", " ")[:160]
        typer.echo(
            f"{h.score:.3f}  {p['note_path']}  [{p['heading_path']}]{page}\n       {snippet}"
        )


@app.command()
def stats() -> None:
    """Notas y chunks indexados."""
    svc = _build()
    notes, chunks = svc.manifest.totals()
    typer.echo(f"notas={notes} chunks_manifest={chunks} puntos_qdrant={svc.store.count()}")


if __name__ == "__main__":
    app()
