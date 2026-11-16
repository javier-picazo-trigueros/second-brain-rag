from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    manifest_path: Path = Path("data/manifest.sqlite")
    chunk_max_chars: int = Field(1800, ge=400)
    chunk_min_chars: int = Field(300, ge=50)

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
