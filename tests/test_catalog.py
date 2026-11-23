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

    def note_links(self) -> dict[str, tuple[str, ...]]:
        return {}


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


# --- enlaces [[...]] por título y notas que enlazan -----------------------------------------------


class Meta:
    def __init__(self, links: dict[str, tuple[str, ...]] | None = None) -> None:
        self.links = links or {}
        self.link_calls = 0

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        return {}

    def note_links(self) -> dict[str, tuple[str, ...]]:
        self.link_calls += 1
        return self.links


def with_links(
    tmp_path: Path, m: Manifest, links: dict[str, tuple[str, ...]] | None = None
) -> Catalog:
    settings = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    return Catalog(settings, m, Meta(links), aliases={})


def test_a_link_resolves_by_title_ignoring_case(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/Tema 1.md", "3º/Redes/Otra.md")
    catalog = with_links(tmp_path, manifest)
    assert catalog.resolve_link("tema 1") == ["3º/Redes/Tema 1.md"]
    assert catalog.resolve_link("  Tema 1  ") == ["3º/Redes/Tema 1.md"]


def test_a_link_resolves_by_path_with_or_without_extension(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "3º/Redes/Tema 1.md")
    catalog = with_links(tmp_path, manifest)
    assert catalog.resolve_link("3º/Redes/Tema 1") == ["3º/Redes/Tema 1.md"]
    assert catalog.resolve_link("3º/Redes/Tema 1.md") == ["3º/Redes/Tema 1.md"]


def test_a_title_in_two_different_notes_gives_every_candidate(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "3º/Redes/Intro.md", "3º/DM/Intro.md")
    assert with_links(tmp_path, manifest).resolve_link("Intro") == [
        "3º/DM/Intro.md",
        "3º/Redes/Intro.md",
    ]


def test_exact_copies_count_as_one_candidate(tmp_path: Path, manifest: Manifest) -> None:
    manifest.upsert("1º/D/Tema 5.md", "h", 2)
    manifest.set_meta("1º/D/Tema 5.md", (), "g")
    manifest.upsert("3º/D/Tema 5.md", "h", 2)
    manifest.set_meta("3º/D/Tema 5.md", (), "g")
    assert with_links(tmp_path, manifest).resolve_link("Tema 5") == ["1º/D/Tema 5.md"]


def test_a_link_to_nothing_gives_no_candidates(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "3º/Redes/Tema 1.md")
    assert with_links(tmp_path, manifest).resolve_link("No existe") == []


def test_backlinks_are_the_notes_whose_links_resolve_to_this_one(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "a/Tema 1.md", "a/Tema 2.md", "b/Resumen.md", "b/Suelta.md")
    links = {
        "a/Tema 2.md": ("Tema 1",),
        "b/Resumen.md": ("tema 1", "Tema 2", "Inventada"),
        "b/Suelta.md": ("Tema 2",),
        "a/Tema 1.md": ("Tema 1",),  # un enlace a sí misma no cuenta
    }
    catalog = with_links(tmp_path, manifest, links)
    assert catalog.backlinks("a/Tema 1.md") == ["a/Tema 2.md", "b/Resumen.md"]
    assert catalog.backlinks("a/Tema 2.md") == ["b/Resumen.md", "b/Suelta.md"]
    assert catalog.backlinks("b/Suelta.md") == []


def test_links_are_read_once_per_index_state(tmp_path: Path, manifest: Manifest) -> None:
    add(manifest, "a/Tema 1.md", "a/Tema 2.md")
    meta = Meta({"a/Tema 2.md": ("Tema 1",)})
    settings = Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]
    catalog = Catalog(settings, manifest, meta, aliases={})
    catalog.backlinks("a/Tema 1.md")
    catalog.backlinks("a/Tema 2.md")
    assert meta.link_calls == 1


def _copies(manifest: Manifest) -> None:
    for p in ("1º/D/Tema 5.md", "3º/D/Tema 5.md", "3º/C/Tema 5.md"):
        manifest.upsert(p, "h", 2)
        manifest.set_meta(p, (), "g")


def test_among_exact_copies_the_one_nearest_to_the_linking_note_wins(
    tmp_path: Path, manifest: Manifest
) -> None:
    _copies(manifest)
    catalog = with_links(tmp_path, manifest)
    assert catalog.resolve_link("Tema 5", near="3º/D/Resumen.md") == ["3º/D/Tema 5.md"]
    assert catalog.resolve_link("Tema 5", near="3º/C/Otra.md") == ["3º/C/Tema 5.md"]
    assert catalog.resolve_link("Tema 5", near="1º/D/Otra.md") == ["1º/D/Tema 5.md"]


def test_without_a_reference_note_the_canonical_copy_is_used(
    tmp_path: Path, manifest: Manifest
) -> None:
    _copies(manifest)
    catalog = with_links(tmp_path, manifest)
    assert catalog.resolve_link("Tema 5") == catalog.resolve_link("Tema 5", near=None)
    assert len(catalog.resolve_link("Tema 5")) == 1


def test_proximity_never_hides_a_different_note_with_the_same_title(
    tmp_path: Path, manifest: Manifest
) -> None:
    _copies(manifest)
    add(manifest, "3º/D/Otra carpeta/Tema 5.md")  # contenido distinto: no es una copia
    found = with_links(tmp_path, manifest).resolve_link("Tema 5", near="3º/D/x.md")
    assert sorted(found) == ["3º/D/Otra carpeta/Tema 5.md", "3º/D/Tema 5.md"]


def test_an_explicit_link_to_a_version_keeps_pointing_at_that_note(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "3º/DM/Unit 5.md", "3º/DM/Unit 5 (1).md")
    catalog = make(tmp_path, manifest, Tags({}))
    assert catalog.resolve_link("Unit 5") == ["3º/DM/Unit 5.md"]
    assert catalog.resolve_link("Unit 5 (1)") == ["3º/DM/Unit 5 (1).md"]


def test_backlinks_do_not_list_a_version_of_the_note_itself(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "3º/DM/Unit 5.md", "3º/DM/Unit 5 (1).md", "3º/DM/Otra.md")
    links = Tags({})
    links.note_links = lambda: {"3º/DM/Unit 5 (1).md": ("Unit 5",), "3º/DM/Otra.md": ("Unit 5",)}  # type: ignore[method-assign]
    catalog = make(tmp_path, manifest, links)
    assert [b for b in catalog.backlinks("3º/DM/Unit 5.md")] == ["3º/DM/Otra.md"]


def test_content_change_refreshes_cached_tags_and_backlinks(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "A.md", "B.md")
    tags = Tags({"A.md": ("antes",)})
    catalog = make(tmp_path, manifest, tags)
    links: dict[str, tuple[str, ...]] = {"A.md": ("B",)}
    tags.note_links = lambda: links  # type: ignore[method-assign]
    assert catalog.note_tags()["A.md"] == ("antes",)
    assert catalog.backlinks("B.md") == ["A.md"]
    tags.data = {"A.md": ("despues",)}
    links.clear()
    manifest.upsert("A.md", "nuevo", 2)
    assert catalog.note_tags()["A.md"] == ("despues",)
    assert catalog.backlinks("B.md") == []


def test_folder_link_resolves_a_short_vault_path_and_its_backlink(
    tmp_path: Path, manifest: Manifest
) -> None:
    add(manifest, "Curso/Uno/Intro.md", "Curso/Dos/Intro.md", "Resumen.md")
    catalog = with_links(tmp_path, manifest, {"Resumen.md": ("Uno/Intro",)})
    assert catalog.resolve_link("Uno/Intro") == ["Curso/Uno/Intro.md"]
    assert catalog.backlinks("Curso/Uno/Intro.md") == ["Resumen.md"]
    assert catalog.backlinks("Curso/Dos/Intro.md") == []
