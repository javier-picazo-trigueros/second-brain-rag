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


def test_qdrant_default_uses_ipv4_loopback(tmp_path: Path) -> None:
    # "localhost" resuelve antes a ::1 y Docker solo publica IPv4: cada conexión nueva pierde ~2 s.
    assert _settings(tmp_path).qdrant_url == "http://127.0.0.1:6333"


def test_embed_batch_size_default_is_8(tmp_path: Path) -> None:
    # Con la GPU casi llena durante la ingesta, lotes de 16 coincidieron con crashes del runner.
    assert _settings(tmp_path).embed_batch_size == 8


def test_embed_batch_size_does_not_affect_the_fingerprint(tmp_path: Path) -> None:
    other = _settings(tmp_path, embed_batch_size=32)
    assert other.index_fingerprint == _settings(tmp_path).index_fingerprint


# --- parámetros de búsqueda, libros y grafo ----------------------------------------------------


def test_retrieval_defaults(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert (s.candidate_limit, s.prefetch_limit, s.max_chunks_per_note) == (150, 120, 2)
    assert (s.length_penalty_alpha, s.length_ref_chunks) == (0.1, 8)
    assert (s.big_note_chunks, s.big_note_quota, s.quota_override_ratio) == (200, 2, 0.9)
    assert (s.graph_fanout_cap, s.graph_budget, s.graph_min_idf) == (5, 4, 0.0)


def test_no_vault_specific_globs_by_default(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert s.exclude_globs == [] and s.demote_globs == []
    assert s.demote_factor == 0.5


def test_globs_are_read_from_a_semicolon_separated_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("BRAIN_EXCLUDE_GLOBS", "3º/Libros/*; **/borrador*.md ;")
    monkeypatch.setenv("BRAIN_DEMOTE_GLOBS", "*/manual-*.md")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.exclude_globs == ["3º/Libros/*", "**/borrador*.md"]
    assert s.demote_globs == ["*/manual-*.md"]


def test_empty_glob_variable_means_no_globs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("BRAIN_EXCLUDE_GLOBS", "")
    assert Settings(_env_file=None).exclude_globs == []  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("length_penalty_alpha", -0.1),
        ("graph_fanout_cap", 0),
        ("graph_budget", -1),
        ("big_note_quota", -1),
        ("quota_override_ratio", 1.5),
        ("demote_factor", 0.0),
        ("max_chunks_per_note", 0),
    ],
)
def test_out_of_range_parameters_are_rejected(tmp_path: Path, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(tmp_path, **{field: value})


def test_is_excluded_by_directory_file_or_glob(tmp_path: Path) -> None:
    s = _settings(tmp_path, exclude_globs=["3º/Libros/*", "**/borrador*.md"])
    assert s.is_excluded("_conceptos/x.md")
    assert s.is_excluded("1º/.obsidian/workspace.md")
    assert s.is_excluded("CLAUDE.md")
    assert s.is_excluded("3º/Libros/Grande.md")
    assert s.is_excluded("2º/IA/borrador final.md")
    assert not s.is_excluded("2º/IA/Apuntes.md")


def test_is_excluded_is_false_without_rules_for_a_normal_note(tmp_path: Path) -> None:
    assert not _settings(tmp_path).is_excluded("2º/IA/Apuntes.md")


def test_demote_factor_applies_only_to_matching_paths(tmp_path: Path) -> None:
    s = _settings(tmp_path, demote_globs=["*/Manual*.md"], demote_factor=0.4)
    assert s.demotion_for("2º/IA/Manual de C.md") == 0.4
    assert s.demotion_for("2º/IA/Apuntes.md") == 1.0


@pytest.mark.parametrize(
    "override",
    [{"exclude_globs": ["x/*"]}, {"demote_globs": ["x/*"]}, {"length_penalty_alpha": 0.5}],
)
def test_search_and_exclusion_settings_do_not_change_the_fingerprint(
    tmp_path: Path, override: dict[str, object]
) -> None:
    assert (
        _settings(tmp_path, **override).index_fingerprint == _settings(tmp_path).index_fingerprint
    )
