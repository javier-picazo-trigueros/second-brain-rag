from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from secondbrain.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [k for k in os.environ if k.startswith("BRAIN_")]:
        monkeypatch.delenv(key)


def _settings(vault: Path, **overrides: Any) -> Settings:
    return Settings(_env_file=None, vault_path=vault, **overrides)  # type: ignore[call-arg]


def test_missing_vault_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="El vault no existe"):
        _settings(tmp_path / "no-existe")


def test_vault_path_is_resolved(tmp_path: Path) -> None:
    assert _settings(tmp_path).vault_path == tmp_path.resolve()


def test_defaults_exclude_obsidian_concepts_and_archive(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert {".obsidian", "_conceptos", "_archivo", ".git", "node_modules"} <= s.exclude_dirs
    assert {"CLAUDE.md", "_INDICE.md"} <= s.exclude_files


def test_environment_variables_override_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("BRAIN_CHUNK_MAX_CHARS", "1000")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vault_path == tmp_path.resolve()
    assert s.chunk_max_chars == 1000


def test_min_chunk_must_be_smaller_than_max(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="chunk_min_chars"):
        _settings(tmp_path, chunk_max_chars=500, chunk_min_chars=500)


def test_embed_batch_size_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _settings(tmp_path, embed_batch_size=0)


def test_bm25_cache_lives_under_data(tmp_path: Path) -> None:
    assert _settings(tmp_path).bm25_cache_dir == Path("data/fastembed_cache")


def test_fingerprint_is_stable(tmp_path: Path) -> None:
    assert _settings(tmp_path).index_fingerprint == _settings(tmp_path).index_fingerprint


@pytest.mark.parametrize(
    "override",
    [
        {"embed_model": "otro-modelo"},
        {"chunk_max_chars": 1500},
        {"chunk_min_chars": 200},
        {"bm25_language": "english"},
    ],
)
def test_fingerprint_changes_with_indexing_parameters(
    tmp_path: Path, override: dict[str, object]
) -> None:
    assert (
        _settings(tmp_path, **override).index_fingerprint != _settings(tmp_path).index_fingerprint
    )


def test_fingerprint_ignores_unrelated_settings(tmp_path: Path) -> None:
    other = _settings(tmp_path, qdrant_url="http://otro:6333", embed_on_cpu=True)
    assert other.index_fingerprint == _settings(tmp_path).index_fingerprint
