from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from secondbrain.retrieval.families import CopyFamilies, base_title, has_version_suffix
from secondbrain.store.manifest import Manifest


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[Manifest]:
    m = Manifest(tmp_path / "m.sqlite")
    yield m
    m.close()


def add(m: Manifest, path: str, chunks: int = 5, body: str | None = None) -> None:
    m.upsert(path, "h", chunks)
    m.set_meta(path, (), body)


def subject(path: str) -> str | None:
    parts = path.split("/")
    return parts[1] if len(parts) > 2 else None


@pytest.mark.parametrize(
    ("stem", "base", "suffix"),
    [
        ("DM - Unit 5 - Classification", "dm - unit 5 - classification", False),
        ("DM - Unit 5 - Classification (1)", "dm - unit 5 - classification", True),
        ("Tema 3 copia", "tema 3", True),
        ("Tema 3 - copia", "tema 3", True),
        ("Tema 3 - Copia (2)", "tema 3", True),
        ("Tema 3 copy", "tema 3", True),
        ("Tema 3 (1) (2)", "tema 3", True),
        ("Tema  3  (1)", "tema 3", True),
        ("Tema 3 (borrador)", "tema 3 (borrador)", False),
        ("Resumen 2023 (2024)", "resumen 2023 (2024)", False),  # no es «(n)» pequeño: un año
        ("Copiador de apuntes", "copiador de apuntes", False),
    ],
)
def test_base_title_strips_only_copy_suffixes(stem: str, base: str, suffix: bool) -> None:
    assert base_title(stem) == base
    assert has_version_suffix(stem) is suffix


def test_versions_with_a_numeric_suffix_in_the_same_subject_form_a_family(
    manifest: Manifest,
) -> None:
    add(manifest, "3º/DM/DM - Unit 5 - Classification.md", 100, body="a")
    add(manifest, "3º/DM/DM - Unit 5 - Classification (1).md", 140, body="b")  # distinto contenido
    add(manifest, "3º/DM/DM - Unit 6.md", 10, body="c")
    families = CopyFamilies(manifest, subject)
    assert families.groups() == [
        ("3º/DM/DM - Unit 5 - Classification (1).md", "3º/DM/DM - Unit 5 - Classification.md")
    ]


def test_the_representative_is_the_one_without_suffix_even_with_fewer_chunks(
    manifest: Manifest,
) -> None:
    add(manifest, "3º/DM/Unit 5.md", 10, body="a")
    add(manifest, "3º/DM/Unit 5 (1).md", 99, body="b")
    families = CopyFamilies(manifest, subject)
    assert families.representative(families.groups()[0]) == "3º/DM/Unit 5.md"


def test_without_a_plain_title_the_representative_has_the_most_chunks(manifest: Manifest) -> None:
    add(manifest, "3º/DM/Unit 5 (1).md", 10, body="a")
    add(manifest, "3º/DM/Unit 5 (2).md", 30, body="b")
    add(manifest, "3º/DM/Unit 5 copia.md", 20, body="c")
    families = CopyFamilies(manifest, subject)
    (group,) = families.groups()
    assert len(group) == 3
    assert families.representative(group) == "3º/DM/Unit 5 (2).md"


def test_a_family_may_span_folders_that_belong_to_the_same_subject(manifest: Manifest) -> None:
    # `subject_of` es la asignatura canónica (con alias): aquí las dos carpetas son la misma.
    add(manifest, "3º/DM/Unit 5.md", 10, body="a")
    add(manifest, "3º/IA II/Unit 5 (1).md", 12, body="b")
    families = CopyFamilies(manifest, lambda p: "Data Mining")
    assert len(families.groups()) == 1


def test_the_same_title_in_different_subjects_is_not_a_family(manifest: Manifest) -> None:
    add(manifest, "3º/DM/Intro.md", 10, body="a")
    add(manifest, "3º/Redes/Intro (1).md", 10, body="b")
    assert CopyFamilies(manifest, subject).groups() == []


def test_equal_titles_without_any_suffix_are_not_merged(manifest: Manifest) -> None:
    add(manifest, "3º/DM/a/Intro.md", 10, body="a")
    add(manifest, "3º/DM/b/Intro.md", 10, body="b")
    assert CopyFamilies(manifest, subject).groups() == []


def test_exact_copies_still_group_even_across_subjects_and_merge_with_versions(
    manifest: Manifest,
) -> None:
    add(manifest, "1º/DISCRETAS/Resumen.md", 10, body="same")
    add(manifest, "3º/Discretas/Resumen.md", 10, body="same")  # copia exacta (otra carpeta)
    add(manifest, "3º/Discretas/Resumen (1).md", 11, body="other")  # versión de la anterior
    families = CopyFamilies(manifest, lambda p: "Matemática Discreta")
    (group,) = families.groups()
    assert set(group) == {
        "1º/DISCRETAS/Resumen.md",
        "3º/Discretas/Resumen.md",
        "3º/Discretas/Resumen (1).md",
    }


def test_exact_copies_group_without_a_subject_function(manifest: Manifest) -> None:
    add(manifest, "a/x.md", 3, body="same")
    add(manifest, "b/x.md", 3, body="same")
    add(manifest, "a/x (1).md", 4, body="other")
    families = CopyFamilies(manifest)  # sin asignaturas: solo copias exactas
    assert families.groups() == [("a/x.md", "b/x.md")]


def test_notes_without_a_subject_never_form_versions(manifest: Manifest) -> None:
    add(manifest, "Suelta.md", 3, body="a")
    add(manifest, "Suelta (1).md", 3, body="b")
    assert CopyFamilies(manifest, lambda p: None).groups() == []


def test_index_maps_every_member_to_its_representative(manifest: Manifest) -> None:
    add(manifest, "3º/DM/Unit 5.md", 10, body="a")
    add(manifest, "3º/DM/Unit 5 (1).md", 12, body="b")
    canonical, others = CopyFamilies(manifest, subject).index()
    assert canonical == {
        "3º/DM/Unit 5.md": "3º/DM/Unit 5.md",
        "3º/DM/Unit 5 (1).md": "3º/DM/Unit 5.md",
    }
    assert others == {"3º/DM/Unit 5.md": ("3º/DM/Unit 5 (1).md",)}


def test_it_notices_notes_added_later(manifest: Manifest) -> None:
    add(manifest, "3º/DM/Unit 5.md", 10, body="a")
    families = CopyFamilies(manifest, subject)
    assert families.groups() == []
    add(manifest, "3º/DM/Unit 5 (1).md", 12, body="b")
    assert len(families.groups()) == 1


def test_a_version_does_not_glue_together_several_unrelated_notes_with_the_same_title(
    manifest: Manifest,
) -> None:
    # Regresión sobre el vault real: 20 «README.md» de prácticas distintas y un «README(4).md».
    for n in (1, 2, 3):
        add(manifest, f"3º/DIS/p0{n}/README.md", 5, body=f"b{n}")
    add(manifest, "3º/DIS/p04/README (4).md", 5, body="b4")
    assert CopyFamilies(manifest, subject).groups() == []


def test_versions_without_an_original_group_only_within_the_same_folder(
    manifest: Manifest,
) -> None:
    add(manifest, "3º/DM/a/Notas (1).md", 5, body="a")
    add(manifest, "3º/DM/a/Notas (2).md", 6, body="b")
    add(manifest, "3º/DM/b/Notas (1).md", 7, body="c")
    assert CopyFamilies(manifest, subject).groups() == [
        ("3º/DM/a/Notas (1).md", "3º/DM/a/Notas (2).md")
    ]


def test_every_version_joins_the_single_original_even_from_another_folder(
    manifest: Manifest,
) -> None:
    add(manifest, "3º/IA II/Unit 5.md", 5, body="a")
    add(manifest, "3º/DM/Unit 5 (1).md", 6, body="b")
    add(manifest, "3º/DM/Unit 5 (2).md", 7, body="c")
    families = CopyFamilies(manifest, lambda p: "Data Mining")
    (group,) = families.groups()
    assert len(group) == 3 and families.representative(group) == "3º/IA II/Unit 5.md"
