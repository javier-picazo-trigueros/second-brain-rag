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


# --- grafo de conceptos, copias y tamaños ----------------------------------------------------


def test_set_meta_stores_concepts_per_note(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h", 1)
    manifest.upsert("b.md", "h", 1)
    manifest.set_meta("a.md", ["x", "y"], None)
    manifest.set_meta("b.md", ["y"], None)
    assert manifest.note_concepts() == {"a.md": ("x", "y"), "b.md": ("y",)}


def test_set_meta_replaces_previous_concepts(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h", 1)
    manifest.set_meta("a.md", ["x", "y"], None)
    manifest.set_meta("a.md", ["z"], None)
    assert manifest.note_concepts() == {"a.md": ("z",)}


def test_notes_without_concepts_are_listed_with_an_empty_tuple(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h", 1)
    assert manifest.note_concepts() == {"a.md": ()}


def test_set_meta_on_unknown_note_is_an_error(manifest: Manifest) -> None:
    with pytest.raises(KeyError, match=r"a.md"):
        manifest.set_meta("a.md", ["x"], None)


def test_delete_also_removes_the_concepts(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h", 1)
    manifest.set_meta("a.md", ["x"], "hash")
    manifest.delete("a.md")
    assert manifest.note_concepts() == {}
    assert manifest.duplicate_groups() == []


def test_duplicate_groups_collect_notes_with_the_same_body_hash(manifest: Manifest) -> None:
    for path, body in (("a.md", "H1"), ("b (1).md", "H1"), ("c.md", "H2"), ("d.md", None)):
        manifest.upsert(path, "h", 1)
        manifest.set_meta(path, [], body)
    assert manifest.duplicate_groups() == [("a.md", "b (1).md")]


def test_notes_without_body_hash_never_form_groups(manifest: Manifest) -> None:
    for path in ("a.md", "b.md"):
        manifest.upsert(path, "h", 1)
        manifest.set_meta(path, [], None)
    assert manifest.duplicate_groups() == []


def test_chunk_counts_per_note(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h", 7)
    manifest.upsert("b.md", "h", 0)
    assert manifest.chunk_counts() == {"a.md": 7, "b.md": 0}


def test_upsert_keeps_meta_of_the_note(manifest: Manifest) -> None:
    manifest.upsert("a.md", "h1", 1)
    manifest.set_meta("a.md", ["x"], "hash")
    manifest.upsert("a.md", "h2", 5)
    assert manifest.note_concepts() == {"a.md": ("x",)}


def test_opens_a_database_created_before_the_meta_columns(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "old.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE notes (path TEXT PRIMARY KEY, hash TEXT NOT NULL, n_chunks INTEGER NOT NULL)"
    )
    con.execute("INSERT INTO notes VALUES ('a.md', 'h', 3)")
    con.commit()
    con.close()
    m = Manifest(db)
    try:
        assert m.get("a.md") == "h"
        m.set_meta("a.md", ["x"], "hash")
        assert m.note_concepts() == {"a.md": ("x",)}
    finally:
        m.close()


# --- valores sueltos (última sincronización...) ---------------------------------------------------


def test_values_default_to_none(manifest: Manifest) -> None:
    assert manifest.get_value("last_sync") is None


def test_values_are_stored_and_overwritten(manifest: Manifest) -> None:
    manifest.set_value("last_sync", "2026-11-16T10:00:00+00:00")
    manifest.set_value("last_sync", "2026-11-16T11:00:00+00:00")
    assert manifest.get_value("last_sync") == "2026-11-16T11:00:00+00:00"


def test_values_persist_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "manifest.sqlite"
    first = Manifest(db)
    first.set_value("k", "v")
    first.close()
    second = Manifest(db)
    try:
        assert second.get_value("k") == "v"
    finally:
        second.close()
