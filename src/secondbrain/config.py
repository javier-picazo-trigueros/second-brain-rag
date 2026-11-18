from __future__ import annotations

import hashlib
import os
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from secondbrain.ingest.chunker import CHUNKER_VERSION

# Raíz del repositorio (src/secondbrain/config.py -> ../..). Las rutas relativas y el .env se
# resuelven desde aquí y no desde el directorio de trabajo: Claude Code lanza el servidor MCP
# desde otro directorio.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BRAIN_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    vault_path: Path
    exclude_dirs: frozenset[str] = frozenset(
        {
            ".obsidian",
            ".git",
            ".trash",
            "node_modules",
            "__MACOSX",
            ".venv",
            "venv",
            "_conceptos",
            "_generadas",  # apuntes que genera la propia herramienta: no se reindexan
            "_archivo",
            "_pruebas",
        }
    )
    exclude_files: frozenset[str] = frozenset({"CLAUDE.md", "_INDICE.md"})
    # Patrones sobre la ruta relativa al vault (con "/"); `*` casa también "/". Van en .env,
    # separados por ";". Excluir quita las notas del índice; rebajar solo reduce su score al buscar.
    exclude_globs: Annotated[list[str], NoDecode] = Field(default_factory=list)
    demote_globs: Annotated[list[str], NoDecode] = Field(default_factory=list)
    demote_factor: float = Field(0.5, gt=0, le=1)

    # Nombre del vault en Obsidian (enlaces «Abrir en Obsidian»); por defecto, el de la carpeta.
    obsidian_vault: str | None = None

    ollama_url: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    embed_batch_size: int = Field(8, ge=1, le=128)
    embed_on_cpu: bool = False
    embed_keep_alive: str = "30m"  # el embedder de consulta (CPU) no se descarga entre preguntas

    qdrant_url: str = "http://127.0.0.1:6333"
    collection: str = "vault_chunks"
    bm25_language: str = "spanish"
    # Caché del modelo BM25 de fastembed: se descarga una vez y después funciona offline.
    bm25_cache_dir: Path = Path("data/fastembed_cache")

    # Modelo de lenguaje (respuestas). En consulta el embedder va en CPU para dejar la VRAM al LLM.
    llm_model: str = "qwen2.5:7b"
    llm_num_ctx: int = Field(16384, ge=2048)
    llm_max_tokens: int = Field(1024, ge=1)  # tope de la respuesta (num_predict)
    llm_temperature: float = Field(0.2, ge=0, le=1)
    llm_keep_alive: str = "10m"

    # Búsqueda híbrida. Los valores por defecto son un punto de partida: los ajustan los evals.
    candidate_limit: int = Field(150, ge=1)  # chunks fusionados que se piden a Qdrant
    prefetch_limit: int = Field(120, ge=1)  # candidatos por rama (denso / BM25) antes de fusionar
    max_chunks_per_note: int = Field(2, ge=1)
    length_penalty_alpha: float = Field(0.1, ge=0)  # penalización por nº de chunks de la nota
    length_ref_chunks: int = Field(8, ge=1)  # una nota con estos chunks o menos no se penaliza
    big_note_chunks: int = Field(200, ge=1)  # a partir de aquí una nota cuenta como "grande"
    big_note_quota: int = Field(2, ge=0)  # máximo de notas grandes en el top-k...
    quota_override_ratio: float = Field(0.9, gt=0, le=1)  # ...salvo que casi igualen al primero
    # Corte por relevancia: una nota es evidencia solo si el coseno de su mejor chunk llega a
    # `min_note_cosine` y no queda más de `cosine_margin` por debajo de la mejor nota.
    min_note_cosine: float = Field(0.55, ge=0, le=1)
    cosine_margin: float = Field(0.12, ge=0, le=1)

    # Visión general ("de qué trata X", "qué se da en el tema N"): notas por asignatura y apartados.
    aliases_path: Path = Path("data/aliases.toml")
    overview_max_notes: int = Field(22, ge=1)
    overview_text_chars: int = Field(350, ge=100)  # texto por nota en una visión de asignatura
    overview_per_topic: int = Field(2, ge=1)  # notas por «tema N» antes de repetir tema
    overview_headings_subject: int = Field(5, ge=0)
    overview_headings_topic: int = Field(25, ge=0)

    # Contexto que se da al LLM (tokens estimados). El total del prompt más la respuesta debe caber
    # en `llm_num_ctx`: sistema ~450 + contexto + pregunta ~700 + `llm_max_tokens`.
    context_budget_tokens: int = Field(4500, ge=500)
    related_budget_tokens: int = Field(800, ge=0)  # parte del anterior reservada a las pistas
    # Modo «ejercicios»: enunciados, soluciones y teoría del tema caben en un contexto mayor.
    exercises_budget_tokens: int = Field(7000, ge=1000)  # estimados; ~1,5x en texto numérico
    exercises_max_tokens: int = Field(2000, ge=1)  # tope de la respuesta en este modo
    # Modo «apuntes»: se escribe por partes; cada una ve una ventana de fragmentos reales.
    notes_window_tokens: int = Field(3000, ge=500)  # tokens estimados de fuentes por parte
    notes_part_max_tokens: int = Field(2000, ge=100)  # tope de cada parte escrita
    notes_skeleton_chars: int = Field(1500, ge=0)  # del resumen del tema que acompaña a cada parte
    exercises_theory_notes: int = Field(2, ge=0)  # notas de teoría que acompañan a los ejercicios

    # API HTTP: solo escucha en la propia máquina. El front de desarrollo (Vite) necesita su origen
    # en `api_cors_origins`, separado por ";"; en producción la sirve la propia API y no hace falta.
    api_host: str = "127.0.0.1"
    api_port: int = Field(8000, ge=1, le=65535)
    api_cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Servidor MCP: todo lo que devuelve pasa a la conversación del cliente (p. ej. Claude Code),
    # así que las salidas están acotadas.
    mcp_max_chars: int = Field(20_000, ge=1_000)  # máximo de texto de nota por llamada
    mcp_snippet_chars: int = Field(400, ge=50)  # tamaño de cada fragmento en los resultados

    # Respuestas
    answer_k: int = Field(5, ge=1)  # notas que se recuperan para responder
    # Coseno mínimo del mejor chunk para considerar fiable el contexto. Es un aviso, no un bloqueo.
    confidence_threshold: float = Field(0.6, ge=0, le=1)

    # Grafo de conceptos
    graph_fanout_cap: int = Field(5, ge=1)  # vecinas máximas por concepto
    graph_budget: int = Field(4, ge=0)  # notas relacionadas máximas por búsqueda
    graph_min_idf: float = Field(0.0, ge=0)  # ignora conceptos más genéricos que este idf

    manifest_path: Path = Path("data/manifest.sqlite")
    chunk_max_chars: int = Field(1800, ge=400)
    chunk_min_chars: int = Field(300, ge=50)

    @field_validator("exclude_globs", "demote_globs", "api_cors_origins", mode="before")
    @classmethod
    def _split_globs(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [part.strip() for part in v.split(";") if part.strip()]
        return v

    @field_validator("manifest_path", "bm25_cache_dir", "aliases_path")
    @classmethod
    def _anchor_to_project_root(cls, v: Path) -> Path:
        return v if v.is_absolute() else PROJECT_ROOT / v

    @field_validator("vault_path")
    @classmethod
    def _vault_exists(cls, v: Path) -> Path:
        if not v.is_dir():
            raise ValueError(f"El vault no existe: {v}")
        return v.resolve()

    @model_validator(mode="after")
    def _min_below_max(self) -> Settings:
        if self.chunk_min_chars >= self.chunk_max_chars:
            raise ValueError("chunk_min_chars debe ser menor que chunk_max_chars")
        if self.related_budget_tokens >= self.context_budget_tokens:
            raise ValueError("related_budget_tokens debe ser menor que context_budget_tokens")
        return self

    @property
    def obsidian_vault_name(self) -> str:
        return self.obsidian_vault or self.vault_path.name

    def is_excluded(self, rel_path: str) -> bool:
        """¿Debe ignorarse esta nota (ruta relativa al vault, con "/")?"""
        *folders, name = rel_path.split("/")
        return (
            any(f in self.exclude_dirs for f in folders)
            or name in self.exclude_files
            or any(fnmatchcase(rel_path, g) for g in self.exclude_globs)
        )

    def demotion_for(self, rel_path: str) -> float:
        """Factor que multiplica el score de la nota al buscar (1.0 = sin rebaja)."""
        return (
            self.demote_factor if any(fnmatchcase(rel_path, g) for g in self.demote_globs) else 1.0
        )

    @property
    def index_fingerprint(self) -> str:
        """Huella de los parámetros que afectan al contenido indexado.

        Si cambia, hay que reindexar todas las notas aunque su contenido sea el mismo.
        """
        parts = (
            self.embed_model,
            str(self.chunk_max_chars),
            str(self.chunk_min_chars),
            self.bm25_language,
            f"chunker-v{CHUNKER_VERSION}",
            "wikilinks-with-path",
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def load_settings() -> Settings:
    """Configuración de la aplicación: `.env` de la raíz del proyecto, o el de `BRAIN_ENV_FILE`."""
    env_file = os.environ.get("BRAIN_ENV_FILE")
    return Settings(_env_file=env_file or PROJECT_ROOT / ".env")  # type: ignore[call-arg]
