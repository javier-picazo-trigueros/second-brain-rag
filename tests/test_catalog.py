from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from secondbrain.config import Settings
from secondbrain.retrieval.catalog import Catalog
from secondbrain.store.manifest import Manifest


class Tags:
    def __init__(self, data: dict[str, tuple[str, ...]]) -> None:
        self.data = data
        self.calls = 0

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        self.calls += 1
        return self.data


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "m.sqlite")
    yield m
    m.close()


def add(m: Manifest, *paths: str) -> None:
    for p in paths:
        m.upsert(p, "h", 2)
        m.set_meta(p, (), None)


def make(tmp_path: Path, m: Manifest, tags: Tags) -> Catalog:
    settings = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    return Catalog(settings, m, tags, aliases={})


def test_subject_and_course_of_a_note(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/Tema 1.md", "Suelta.md")
    catalog = make(tmp_path, manifest, Tags({}))
    assert catalog.subject_name("3º/Redes/Tema 1.md") == "Redes"
    assert catalog.course("3º/Redes/Tema 1.md") == "3º"
    assert catalog.subject_name("Suelta.md") is None and catalog.course("Suelta.md") is None


def test_subjects_are_listed_with_their_note_count(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/a.md", "3º/Redes/b.md", "3º/DM/c.md")
    assert make(tmp_path, manifest, Tags({})).subjects() == [("DM", 1), ("Redes", 2)]


def test_it_sees_new_notes_without_being_rebuilt(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/a.md")
    catalog = make(tmp_path, manifest, Tags({}))
    assert catalog.subjects() == [("Redes", 1)]
    add(manifest, "3º/DM/b.md")
    assert catalog.subjects() == [("DM", 1), ("Redes", 1)]


def test_tags_are_read_once_per_index_state(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/a.md")
    tags = Tags({"3º/Redes/a.md": ("red",)})
    catalog = make(tmp_path, manifest, tags)
    assert catalog.note_tags()["3º/Redes/a.md"] == ("red",)
    catalog.note_tags()
    assert tags.calls == 1
    add(manifest, "3º/Redes/b.md")
    catalog.note_tags()
    assert tags.calls == 2
