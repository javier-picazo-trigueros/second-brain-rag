from __future__ import annotations

import hashlib
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from secondbrain.ingest.chunker import CHUNKER_VERSION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRAIN_", env_file=".env", extra="ignore")

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

    ollama_url: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    embed_batch_size: int = Field(8, ge=1, le=128)
    embed_on_cpu: bool = False
    embed_keep_alive: str = "30s"

    qdrant_url: str = "http://127.0.0.1:6333"
    collection: str = "vault_chunks"
    bm25_language: str = "spanish"
    # Caché del modelo BM25 de fastembed: se descarga una vez y después funciona offline.
    bm25_cache_dir: Path = Path("data/fastembed_cache")

    # Búsqueda híbrida. Los valores por defecto son un punto de partida: los ajustan los evals.
    candidate_limit: int = Field(150, ge=1)  # chunks fusionados que se piden a Qdrant
    prefetch_limit: int = Field(120, ge=1)  # candidatos por rama (denso / BM25) antes de fusionar
    max_chunks_per_note: int = Field(2, ge=1)
    length_penalty_alpha: float = Field(0.1, ge=0)  # penalización por nº de chunks de la nota
    length_ref_chunks: int = Field(8, ge=1)  # una nota con estos chunks o menos no se penaliza
    big_note_chunks: int = Field(200, ge=1)  # a partir de aquí una nota cuenta como "grande"
    big_note_quota: int = Field(2, ge=0)  # máximo de notas grandes en el top-k...
    quota_override_ratio: float = Field(0.9, gt=0, le=1)  # ...salvo que casi igualen al primero

    # Grafo de conceptos
    graph_fanout_cap: int = Field(5, ge=1)  # vecinas máximas por concepto
    graph_budget: int = Field(4, ge=0)  # notas relacionadas máximas por búsqueda
    graph_min_idf: float = Field(0.0, ge=0)  # ignora conceptos más genéricos que este idf

    manifest_path: Path = Path("data/manifest.sqlite")
    chunk_max_chars: int = Field(1800, ge=400)
    chunk_min_chars: int = Field(300, ge=50)

    @field_validator("exclude_globs", "demote_globs", mode="before")
    @classmethod
    def _split_globs(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [part.strip() for part in v.split(";") if part.strip()]
        return v

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
        return self

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
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
