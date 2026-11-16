from __future__ import annotations

import httpx
from fastapi import FastAPI

from secondbrain.answer.llm import OllamaLLM
from secondbrain.answer.pipeline import AnswerPipeline
from secondbrain.api.app import AppServices, create_app
from secondbrain.api.health import HealthChecker
from secondbrain.api.reindex import ReindexManager
from secondbrain.config import Settings, load_settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.retrieval.overview import IntentRetriever
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore


def build_services(settings: Settings | None = None) -> AppServices:
    """Cablea los servicios reales. No exige que Ollama ni Qdrant estén arrancados: si no lo
    están, `/health` lo cuenta y las demás rutas responden 503 con cómo arrancarlos."""
    # En consulta el embedder va en CPU: la VRAM es para el LLM.
    s = (settings or load_settings()).model_copy(update={"embed_on_cpu": True})
    embedder = OllamaEmbedder(s)
    store = VectorStore(s, dim=None)  # solo lectura de la colección: no necesita la dimensión
    manifest = Manifest(s.manifest_path)
    retriever = HybridRetriever(s, embedder, store, manifest)
    answers = IntentRetriever(s, retriever, store, manifest)  # visión general o búsqueda
    indexer = Indexer(s, embedder, store, manifest)
    health = HealthChecker(s, httpx.Client(base_url=s.ollama_url), store.count)
    return AppServices(
        settings=s,
        retriever=retriever,
        pipeline=AnswerPipeline(s, answers, OllamaLLM(s)),
        manifest=manifest,
        health=health.check,
        reindex=ReindexManager(lambda progress: indexer.sync(on_progress=progress)),
        points=store.count,
    )


def create_app_from_env() -> FastAPI:
    """Fábrica para uvicorn: `uvicorn secondbrain.api.main:create_app_from_env --factory`."""
    return create_app(build_services())
