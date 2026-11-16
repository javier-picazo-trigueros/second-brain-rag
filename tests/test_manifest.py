from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from secondbrain.store.manifest import Manifest


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "data" / "manifest.sqlite")
    yield m
    m.close()


def test_creates_parent_directory(tmp_path: Path) -> None:
    db = tmp_path / "nuevo" / "sub" / "manifest.sqlite"
    Manifest(db).close()
    assert db.is_file()


def test_unknown_path_has_no_hash(manifest: Manifest) -> None:
    assert manifest.get("no/existe.md") is None


def test_upsert_then_get(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 3)
    assert manifest.get("a.md") == "h1"


def test_upsert_overwrites_hash_and_chunk_count(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 3)
    manifest.upsert("a.md", "h2", 5)
    assert manifest.get("a.md") == "h2"
    assert manifest.totals() == (1, 5)


def test_delete_removes_note(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 3)
    manifest.delete("a.md")
    assert manifest.get("a.md") is None
    assert manifest.paths() == set()


def test_delete_unknown_path_is_a_noop(manifest: Manifest) -> None:
    manifest.delete("no/existe.md")
    assert manifest.totals() == (0, 0)


def test_paths_lists_all_notes(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 1)
    manifest.upsert("b/c.md", "h2", 2)
    assert manifest.paths() == {"a.md", "b/c.md"}


def test_totals_sum_notes_and_chunks(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 3)
    manifest.upsert("b.md", "h2", 0)
    assert manifest.totals() == (2, 3)


def test_empty_manifest_totals_are_zero(manifest: Manifest) -> None:
    assert manifest.totals() == (0, 0)


def test_data_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "manifest.sqlite"
    first = Manifest(db)
    first.upsert("a.md", "h1", 2)
    first.close()
    second = Manifest(db)
    try:
        assert second.get("a.md") == "h1"
    finally:
        second.close()
