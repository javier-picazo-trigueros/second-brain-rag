"""Entorno de test: vault copiado a un directorio temporal + fakes + manifest real en sqlite."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from secondbrain.config import Settings
from secondbrain.ingest.indexer import Indexer
from secondbrain.store.manifest import Manifest
from tests.fakes import Events, FakeEmbedder, FakeStore


class Env:
    def __init__(self, tmp_path: Path, fixture_vault: Path) -> None:
        self.vault = tmp_path / "vault"
        shutil.copytree(fixture_vault, self.vault)
        self.tmp = tmp_path
        self.events: Events = []
        self.embedder = FakeEmbedder(self.events)
        self.store = FakeStore(self.events)
        self.manifest = Manifest(tmp_path / "data" / "manifest.sqlite")

    def settings(self, **overrides: Any) -> Settings:
        return Settings(  # type: ignore[call-arg]
            _env_file=None,
            vault_path=self.vault,
            manifest_path=self.tmp / "data" / "manifest.sqlite",
            **overrides,
        )

    def indexer(self, **overrides: Any) -> Indexer:
        return Indexer(self.settings(**overrides), self.embedder, self.store, self.manifest)

    def write(self, rel: str, text: str) -> None:
        (self.vault / rel).write_text(text, encoding="utf-8", newline="")
