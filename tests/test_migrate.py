"""Migración de la carpeta de datos (manifest, caché de BM25, alias) sin perder nada."""

from __future__ import annotations

from pathlib import Path

import pytest

from secondbrain.migrate import MigrationError, migrate_data, verify_copy
from secondbrain.store.manifest import Manifest


@pytest.fixture
def source(tmp_path: Path) -> Path:
    data = tmp_path / "origen"
    data.mkdir()
    m = Manifest(data / "manifest.sqlite")
    m.upsert("a.md", "hash-a", 3, generation="gen-a", links_version=1)
    m.upsert("b.md", "hash-b", 5, generation="gen-b")
    m.set_meta("a.md", ("uno", "dos"), "cuerpo-a")
    m.set_value("last_sync", "2026-11-24T10:00:00")
    m.close()
    (data / "aliases.toml").write_text('[subjects."X"]\naliases = ["x"]\n', encoding="utf-8")
    cache = data / "fastembed_cache" / "models--Qdrant--bm25" / "snapshots"
    cache.mkdir(parents=True)
    (cache / "stopwords.txt").write_bytes(b"de\nla\nel\n")
    (data / "fastembed_cache" / "modelo.bin").write_bytes(bytes(range(256)) * 10)
    return data


def test_everything_is_copied_and_the_manifest_is_identical(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "fuera" / "datos"
    report = migrate_data(source, dest)
    assert report.notes == 2 and report.chunks == 8
    assert (dest / "aliases.toml").read_text(encoding="utf-8") == (
        source / "aliases.toml"
    ).read_text(encoding="utf-8")
    assert (dest / "fastembed_cache" / "modelo.bin").read_bytes() == bytes(range(256)) * 10
    m = Manifest(dest / "manifest.sqlite")
    try:
        assert m.paths() == {"a.md", "b.md"}
        assert m.get("a.md") == "hash-a" and m.links_version("a.md") == 1
        assert m.note_concepts()["a.md"] == ("uno", "dos")
        assert m.get_value("last_sync") == "2026-11-24T10:00:00"
    finally:
        m.close()


def test_the_source_is_left_untouched(source: Path, tmp_path: Path) -> None:
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    migrate_data(source, tmp_path / "destino")
    after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert before == after


def test_a_verified_copy_reports_no_problems(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "destino"
    migrate_data(source, dest)
    assert verify_copy(source, dest) == []


def test_verification_detects_a_changed_or_missing_file(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "destino"
    migrate_data(source, dest)
    (dest / "fastembed_cache" / "modelo.bin").write_bytes(b"roto")
    (dest / "aliases.toml").unlink()
    problems = verify_copy(source, dest)
    assert any("modelo.bin" in p for p in problems)
    assert any("aliases.toml" in p for p in problems)


def test_a_manifest_that_lost_rows_is_detected(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "destino"
    migrate_data(source, dest)
    m = Manifest(dest / "manifest.sqlite")
    m.delete("b.md")
    m.close()
    assert any("manifest" in p.lower() for p in verify_copy(source, dest))


def test_a_destination_that_already_has_data_is_refused(source: Path, tmp_path: Path) -> None:
    dest = tmp_path / "destino"
    dest.mkdir()
    (dest / "manifest.sqlite").write_bytes(b"otra cosa")
    with pytest.raises(MigrationError, match="ya tiene"):
        migrate_data(source, dest)
    assert (dest / "manifest.sqlite").read_bytes() == b"otra cosa"


def test_the_destination_cannot_be_the_source_or_live_inside_it(
    source: Path,
) -> None:
    with pytest.raises(MigrationError, match=r"mismo sitio|dentro"):
        migrate_data(source, source)
    with pytest.raises(MigrationError, match=r"mismo sitio|dentro"):
        migrate_data(source, source / "subcarpeta")


def test_a_missing_source_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="no existe"):
        migrate_data(tmp_path / "nada", tmp_path / "destino")


def test_a_source_without_manifest_still_copies_the_rest(tmp_path: Path) -> None:
    source = tmp_path / "origen"
    source.mkdir()
    (source / "aliases.toml").write_text("x = 1\n", encoding="utf-8")
    report = migrate_data(source, tmp_path / "destino")
    assert report.notes == 0
    assert (tmp_path / "destino" / "aliases.toml").exists()


# --- brain migrate-data ------------------------------------------------------------------------


def test_the_command_copies_verifies_and_says_how_to_activate_it(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from secondbrain import cli

    dest = tmp_path / "nuevo-sitio"
    monkeypatch.setattr(cli, "_data_dir", lambda: source)
    result = CliRunner().invoke(cli.app, ["migrate-data", str(dest)])
    assert result.exit_code == 0, result.output
    assert "notas=2" in result.output and "chunks=8" in result.output
    assert f"BRAIN_DATA_DIR={dest.resolve()}" in result.output
    assert (dest / "manifest.sqlite").exists() and (source / "manifest.sqlite").exists()


def test_the_command_fails_without_touching_anything_when_the_destination_has_files(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from secondbrain import cli

    dest = tmp_path / "ocupado"
    dest.mkdir()
    (dest / "algo.txt").write_text("mío", encoding="utf-8")
    monkeypatch.setattr(cli, "_data_dir", lambda: source)
    result = CliRunner().invoke(cli.app, ["migrate-data", str(dest)])
    assert result.exit_code != 0 and "ya tiene" in result.output
    assert [p.name for p in dest.iterdir()] == ["algo.txt"]
