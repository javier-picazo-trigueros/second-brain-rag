from __future__ import annotations

import pytest

from secondbrain.retrieval.topics import (
    clean_title,
    index_topics,
    is_guide,
    topic_key,
    topics_fact,
)

IA2 = [
    "3º/IA II/AIII - Unit 1 - Sample topic one.md",
    "3º/IA II/AIII - Unit 2 - Sample topic two (1).md",
    "3º/IA II/AIII - Unit 2 - Sample topic two.md",
    "3º/IA II/AIII - Unit 3 - Sample topic three.md",
    "3º/IA II/AIII - Unit 4 - Sample exercise 1 (1).md",
    "3º/IA II/AIII - Unit 4 - Sample topic four - Linear.md",
    "3º/IA II/AIII - Unit 5 - Sample topic five - Non-linear (1).md",
    "3º/IA II/AIII - Unit 6 - Sample topic six (Alpha) (2).md",
    "3º/IA II/AIII - Unit 6 - Sample topic six (Beta).md",
    "3º/IA II/AIII - Unit 7 - Sample topic seven.md",
    "3º/IA II/AII - Unit 2 - Sample exercise 1.md",  # ejercicios de la unidad 2
    "3º/IA II/sample-book-title.md",
    "3º/IA II/2401.00001v1.md",
]


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("3º/IA II/AIII - Unit 2 - Redes.md", (2, "2")),
        ("2º/SO/Tema-3.1 Ejemplo de procesos v2021.md", (3, "3.1")),
        ("3º/Redes/Redes_Tema4_V4.md", (4, "4")),
        ("3º/D/Tema 5 Ejemplo de grafos [MD].md", (5, "5")),
        ("1º/DISCRETAS/TEMA 5/figura.md", (5, "5")),  # por la carpeta
        ("3º/D/Tema 1 2024.md", (1, "1")),  # un año no es un subtema
        ("3º/D/Cap 5 Ejemplo de libro.md", None),  # un capítulo de libro no es un tema
        ("3º/IA II/2401.00001v1.md", None),
    ],
)
def test_topic_key_comes_from_the_file_name_or_its_folder(
    path: str, key: tuple[int, str] | None
) -> None:
    assert topic_key(path) == key


@pytest.mark.parametrize(
    ("stem", "clean"),
    [
        ("AIII - Unit 2 - Sample topic two (1)", "Sample topic two"),
        ("Tema-3.1 Ejemplo de procesos v2021", "Ejemplo de procesos"),
        ("Redes_Tema4_V4", ""),
        ("Tema 5 Ejemplo de grafos [MD]", "Ejemplo de grafos [MD]"),
    ],
)
def test_clean_title_drops_the_marker_copies_and_versions(stem: str, clean: str) -> None:
    assert clean_title(stem) == clean


def test_the_number_of_topics_is_the_number_of_distinct_units() -> None:
    topics = index_topics(IA2)
    assert [t.number for t in topics] == [1, 2, 3, 4, 5, 6, 7]
    assert len(topics) == 7


def test_titles_are_the_theory_notes_not_the_exercises() -> None:
    by_number = {t.number: t for t in index_topics(IA2)}
    assert by_number[2].titles == ("Sample topic two",)
    assert by_number[6].titles == (
        "Sample topic six (Alpha)",
        "Sample topic six (Beta)",
    )
    assert by_number[4].titles == ("Sample topic four - Linear",)


def test_a_unit_with_only_exercises_still_counts() -> None:
    topics = index_topics(["3º/X/Unit 1 - Intro.md", "3º/X/Unit 2 - exercise 1.md"])
    assert [t.number for t in topics] == [1, 2]
    assert topics[1].titles == ()


def test_sub_topics_are_one_topic() -> None:
    paths = [f"2º/SO/Tema-3.{n} Cosa {n}.md" for n in (1, 2, 3)] + ["2º/SO/Tema-4.1 Otra.md"]
    assert [(t.number, len(t.titles)) for t in index_topics(paths)] == [(3, 3), (4, 1)]


def test_a_subject_without_numbered_units_has_no_topics() -> None:
    assert index_topics(["3º/X/apuntes.md", "3º/X/practica.md"]) == []


def test_the_fact_states_the_exact_count_and_lists_them() -> None:
    fact = topics_fact(index_topics(IA2))
    assert "7 temas" in fact
    assert "1. Sample topic one" in fact
    assert "2. Sample topic two" in fact
    assert "7. Sample topic seven" in fact
    assert fact.index("1. Sample topic one") < fact.index("2. Sample topic two")


def test_the_fact_reports_gaps_in_the_numbering() -> None:
    fact = topics_fact(index_topics(["a/Unit 1 - A.md", "a/Unit 2 - B.md", "a/Unit 5 - E.md"]))
    assert "3 temas" in fact and "(números: 1, 2, 5)" in fact


def test_the_fact_is_singular_for_one_topic_and_empty_for_none() -> None:
    assert "1 tema " in topics_fact(index_topics(["a/Tema 1 - A.md"]))
    assert topics_fact([]) == ""


@pytest.mark.parametrize(
    ("title", "guide"),
    [
        ("Guía docente Sistemas Operativos", True),
        ("guia_docente_2025", True),
        ("Syllabus", True),
        ("Programa de la asignatura", True),
        ("Tema 1 - Ejemplo de integracion", False),
        ("Temario", False),
        ("Tema-3.1 Ejemplo de procesos v2021", False),
    ],
)
def test_course_guides_are_recognised_by_name(title: str, guide: bool) -> None:
    assert is_guide(title) is guide
