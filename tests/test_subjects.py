from __future__ import annotations

from pathlib import Path

import pytest

from secondbrain.retrieval.intent import detect_intent
from secondbrain.retrieval.subjects import SubjectIndex, load_aliases, norm, subject_of

PATHS = [
    "3º/Discretas/Tema 5 Teoría de grafos [MD].md",
    "3º/Discretas/Resumen Tema 5 [MD] (1).md",
    "3º/Discretas/Tema 4 Teoría de números.md",
    "1º/DISCRETAS/TEMA 5/Tema 5 Teoría de grafos [MD].md",
    "1º/DISCRETAS/TEMA 5/images/figura.md",
    "3º/DM/DM - Unit 1 - Introduction.md",
    "3º/DM/PWI_GROUP1/PWI_GROUP1/RESEARCH.md",
    "3º/IA II/DM - Unit 0 - Introduction.md",
    "3º/IA II/AIII - Unit 2 - Neural Networks.md",
    "2º/SISTEMAS OPERATIVOS/Tema-3.3 Procesos e Hilos en C v2021.md",
    "3º/SISTEMAS/Tema-3.1 Procesos e Hilos v2021.md",
    "3º/SISTEMAS/Tema 3 - Seguridad en Sistemas IT.md",
    "3º/Redes/RSD_25-26__Tema4_V4.md",
    "3º/Redes/RSD_25-26__Tema5_V2.md",
    "Suelta.md",
]

ALIASES = """
[subjects."Sistemas Operativos"]
aliases = ["sistemas operativos", "ssoo"]
folders = ["SISTEMAS OPERATIVOS", "SISTEMAS"]

[subjects."Data Mining"]
aliases = ["data mining", "minería de datos"]
folders = ["DM"]
include = ["IA II/DM - "]

[subjects."Matemática Discreta"]
aliases = ["matemática discreta", "discretas"]
folders = ["Discretas"]
"""


@pytest.fixture
def index(tmp_path: Path) -> SubjectIndex:
    f = tmp_path / "aliases.toml"
    f.write_text(ALIASES, encoding="utf-8")
    return SubjectIndex(PATHS, load_aliases(f))


def test_norm_ignores_case_accents_and_punctuation() -> None:
    assert norm("Matemática  DISCRETA!") == "matematica discreta"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("3º/Discretas/Tema 5.md", "Discretas"),
        (
            "3º/DM/PWI_GROUP1/PWI_GROUP1/RESEARCH.md",
            "DM",
        ),  # la carpeta de asignatura, no la inmediata
        ("1º/DISCRETAS/TEMA 5/images/figura.md", "DISCRETAS"),
        ("Suelta.md", None),
        ("3º/Nota.md", None),  # curso sin asignatura
    ],
)
def test_subject_of_uses_second_level_folder(path: str, expected: str | None) -> None:
    assert subject_of(path) == expected


def test_load_aliases_missing_file_gives_empty_map(tmp_path: Path) -> None:
    assert load_aliases(tmp_path / "no-existe.toml") == {}


def test_load_aliases_rejects_malformed_entry(tmp_path: Path) -> None:
    f = tmp_path / "a.toml"
    f.write_text('[subjects."X"]\naliases = "no es lista"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="aliases"):
        load_aliases(f)


def test_folders_with_different_case_and_courses_are_one_subject() -> None:
    idx = SubjectIndex(PATHS)
    discretas = idx.by_name("discretas")
    assert discretas is not None
    assert "1º/DISCRETAS/TEMA 5/Tema 5 Teoría de grafos [MD].md" in idx.notes_of(discretas)
    assert "3º/Discretas/Tema 4 Teoría de números.md" in idx.notes_of(discretas)


def test_subject_paths_include_nested_folders() -> None:
    idx = SubjectIndex(PATHS)
    dm = idx.by_name("dm")
    assert dm is not None
    assert "3º/DM/PWI_GROUP1/PWI_GROUP1/RESEARCH.md" in idx.notes_of(dm)


def test_alias_file_merges_folders_and_adds_includes(index: SubjectIndex) -> None:
    dm = index.detect("de qué trata data mining")
    assert dm is not None and dm.name == "Data Mining"
    notes = index.notes_of(dm)
    assert "3º/IA II/DM - Unit 0 - Introduction.md" in notes  # por `include`
    assert "3º/DM/DM - Unit 1 - Introduction.md" in notes  # por `folders`
    assert "3º/IA II/AIII - Unit 2 - Neural Networks.md" not in notes
    so = index.detect("la asignatura de sistemas operativos")
    assert so is not None
    so_notes = set(index.notes_of(so))
    assert "2º/SISTEMAS OPERATIVOS/Tema-3.3 Procesos e Hilos en C v2021.md" in so_notes
    assert "3º/SISTEMAS/Tema-3.1 Procesos e Hilos v2021.md" in so_notes


def test_detect_prefers_the_longest_alias(index: SubjectIndex) -> None:
    # "sistemas" es carpeta (alias automático) y "sistemas operativos" alias explícito.
    found = index.detect("qué se da en sistemas operativos")
    assert found is not None and found.name == "Sistemas Operativos"


def test_detect_is_word_based_and_accent_insensitive(index: SubjectIndex) -> None:
    assert index.detect("MATEMATICA DISCRETA, por favor") is not None
    assert index.detect("las discretasmente raras") is None
    assert index.detect("receta de paella") is None


def test_automatic_aliases_come_from_folder_names() -> None:
    idx = SubjectIndex(PATHS)
    found = idx.detect("resume la asignatura de redes")
    assert found is not None and found.name == "Redes"


# --- intención -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "¿De qué trata la asignatura de Data Mining y qué cosas destacarías?",
        "Resúmeme la asignatura de Data Mining",
        "¿Qué temas se ven en la asignatura de sistemas operativos?",
        "temario de data mining",
    ],
)
def test_overview_subject(index: SubjectIndex, question: str) -> None:
    intent = detect_intent(question, index)
    assert intent.kind == "overview_subject"
    assert intent.subject is not None and intent.topic is None


def test_overview_topic(index: SubjectIndex) -> None:
    intent = detect_intent("¿Qué se da en el tema 5 de matemática discreta?", index)
    assert intent.kind == "overview_topic"
    assert intent.topic == 5
    assert intent.subject is not None and intent.subject.name == "Matemática Discreta"


def test_topic_without_a_known_subject_is_a_normal_search(index: SubjectIndex) -> None:
    assert detect_intent("¿Qué se da en el tema 5 de cocina?", index).kind == "search"


def test_concrete_questions_are_normal_searches_even_if_they_name_a_subject(
    index: SubjectIndex,
) -> None:
    for q in (
        "¿Qué diferencia hay entre un proceso y un hilo?",
        "¿Cómo se calcula la entropía en data mining?",
        "¿Qué es un grafo bipartito?",
    ):
        assert detect_intent(q, index).kind == "search"


def test_topic_notes_match_by_name_or_folder(index: SubjectIndex) -> None:
    discretas = index.detect("matemática discreta")
    assert discretas is not None
    notes = index.topic_notes(discretas, 5)
    assert "3º/Discretas/Tema 5 Teoría de grafos [MD].md" in notes
    assert "3º/Discretas/Resumen Tema 5 [MD] (1).md" in notes
    assert "1º/DISCRETAS/TEMA 5/images/figura.md" in notes  # por la carpeta TEMA 5
    assert "3º/Discretas/Tema 4 Teoría de números.md" not in notes
    so = index.detect("sistemas operativos")
    assert so is not None
    assert "3º/SISTEMAS/Tema-3.1 Procesos e Hilos v2021.md" in index.topic_notes(so, 3)
    assert "3º/SISTEMAS/Tema 3 - Seguridad en Sistemas IT.md" in index.topic_notes(so, 3)
