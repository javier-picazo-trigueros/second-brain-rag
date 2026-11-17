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
    "3º/Redes/Redes_Tema4_V4.md",
    "3º/Redes/Redes_Tema5_V2.md",
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


def test_detect_all_returns_every_named_subject_in_question_order(index: SubjectIndex) -> None:
    found = index.detect_all("relación entre data mining y sistemas operativos")
    assert [s.name for s in found] == ["Data Mining", "Sistemas Operativos"]


def test_detect_all_ignores_an_alias_inside_a_longer_one(index: SubjectIndex) -> None:
    # "sistemas" por sí solo no es una asignatura aparte cuando va dentro de "sistemas operativos"
    found = index.detect_all("qué se da en sistemas operativos")
    assert [s.name for s in found] == ["Sistemas Operativos"]


def test_detect_all_of_a_question_without_subjects_is_empty(index: SubjectIndex) -> None:
    assert index.detect_all("receta de paella") == []


# --- una carpeta repartida entre dos asignaturas, y alias como palabra completa ----------------

SPLIT = """
[subjects."Sistemas Operativos"]
aliases = ["sistemas operativos", "so", "ssoo"]
folders = ["SISTEMAS OPERATIVOS"]
include = ["sistemas tema 3 1", "sistemas tema 3 2"]

[subjects."Administración de Sistemas"]
aliases = ["administración de sistemas", "asi", "sistemas", "cloud"]
folders = ["SISTEMAS"]

[subjects."Computación de Alto Rendimiento"]
aliases = ["car"]
folders = ["CAR"]
"""


@pytest.fixture
def split(tmp_path: Path) -> SubjectIndex:
    f = tmp_path / "split.toml"
    f.write_text(SPLIT, encoding="utf-8")
    return SubjectIndex([*PATHS, "4º/CAR/CAR_T1.md"], load_aliases(f))


def test_an_include_moves_notes_out_of_the_other_subjects_folder(split: SubjectIndex) -> None:
    so = split.by_name("Sistemas Operativos")
    asi = split.by_name("Administración de Sistemas")
    assert so is not None and asi is not None
    so_notes, asi_notes = set(split.notes_of(so)), set(split.notes_of(asi))
    assert "3º/SISTEMAS/Tema-3.1 Procesos e Hilos v2021.md" in so_notes
    assert "2º/SISTEMAS OPERATIVOS/Tema-3.3 Procesos e Hilos en C v2021.md" in so_notes
    assert "3º/SISTEMAS/Tema-3.1 Procesos e Hilos v2021.md" not in asi_notes
    assert "3º/SISTEMAS/Tema 3 - Seguridad en Sistemas IT.md" in asi_notes
    assert not so_notes & asi_notes  # ninguna nota en las dos


def test_the_split_subjects_are_told_apart_by_their_alias(split: SubjectIndex) -> None:
    for text, name in [
        ("qué se da en sistemas operativos", "Sistemas Operativos"),
        ("de qué trata la asignatura de ssoo", "Sistemas Operativos"),
        ("temario de administración de sistemas", "Administración de Sistemas"),
        ("resume el cloud", "Administración de Sistemas"),
        ("resume sistemas", "Administración de Sistemas"),
    ]:
        found = split.detect(text)
        assert found is not None and found.name == name, text


@pytest.mark.parametrize(
    "text", ["el carácter especial", "un carro rojo", "descargar el archivo", "escaso", "cargo"]
)
def test_an_alias_never_matches_inside_another_word(split: SubjectIndex, text: str) -> None:
    assert split.detect(f"de qué trata {text}") is None


@pytest.mark.parametrize("text", ["de qué trata car", "resume CAR", "¿Qué es la asignatura CAR?"])
def test_an_alias_matches_as_a_whole_word(split: SubjectIndex, text: str) -> None:
    found = split.detect(text)
    assert found is not None and found.name == "Computación de Alto Rendimiento"


# --- frases informales y alias de IA I / IA II sin ambigüedad -----------------------------------

INFORMAL_ALIASES = """
[subjects."Inteligencia Artificial I"]
aliases = ["ia i", "ia 1", "inteligencia artificial i", "inteligencia artificial 1"]
folders = ["IA I"]

[subjects."Inteligencia Artificial II"]
aliases = ["ia ii", "ia 2", "inteligencia artificial ii", "inteligencia artificial 2"]
folders = ["IA II"]

[subjects."Data Mining"]
aliases = ["data mining", "mineria de datos"]
folders = ["DM"]
include = ["ia ii dm"]

[subjects."Sistemas Operativos"]
aliases = ["sistemas operativos", "so", "ssoo"]
folders = ["SISTEMAS OPERATIVOS"]

[subjects."Matemática Discreta"]
aliases = ["matemática discreta", "discretas"]
folders = ["Discretas"]
"""

INFORMAL_PATHS = [
    "3º/IA I/AII - Unit 1 - Background.md",
    "3º/IA I/AII - Unit 2 - Human intelligence.md",
    "3º/IA II/AIII - Unit 1 - Background.md",
    "3º/IA II/AIII - Unit 2 - Neural Networks.md",
    "3º/IA II/DM - Unit 0 - Introduction.md",
    "3º/DM/DM - Unit 1 - Introduction to Data Mining.md",
    "2º/SISTEMAS OPERATIVOS/Tema 4.1 - Sincronizacion.md",
    "3º/Discretas/Tema 5 Teoría de grafos.md",
    "3º/Redes/Redes_Tema4.md",
]


@pytest.fixture
def informal(tmp_path: Path) -> SubjectIndex:
    f = tmp_path / "informal.toml"
    f.write_text(INFORMAL_ALIASES, encoding="utf-8")
    return SubjectIndex(INFORMAL_PATHS, load_aliases(f))


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("inteligencia artificial II", "Inteligencia Artificial II"),
        ("inteligencia artificial 2", "Inteligencia Artificial II"),
        ("IA II", "Inteligencia Artificial II"),
        ("ia 2", "Inteligencia Artificial II"),
        ("inteligencia artificial I", "Inteligencia Artificial I"),
        ("inteligencia artificial 1", "Inteligencia Artificial I"),
        ("IA I", "Inteligencia Artificial I"),
        ("ia 1", "Inteligencia Artificial I"),
    ],
)
def test_ai_one_and_two_are_never_confused(informal: SubjectIndex, text: str, name: str) -> None:
    found = informal.detect(f"de que trata {text}")
    assert found is not None and found.name == name


def test_dm_notes_inside_the_ia_ii_folder_belong_to_data_mining(informal: SubjectIndex) -> None:
    ia2 = informal.by_name("Inteligencia Artificial II")
    dm = informal.by_name("Data Mining")
    assert ia2 is not None and dm is not None
    assert "3º/IA II/DM - Unit 0 - Introduction.md" in informal.notes_of(dm)
    assert "3º/IA II/DM - Unit 0 - Introduction.md" not in informal.notes_of(ia2)
    assert "3º/IA I/AII - Unit 1 - Background.md" not in informal.notes_of(ia2)


@pytest.mark.parametrize(
    "text",
    [
        "inteligencia artificicial II",
        "inteligenzia artificial 2",
        "inteligencia artifical II",
        "mineria de datoss",
    ],
)
def test_a_misspelled_subject_is_still_found(informal: SubjectIndex, text: str) -> None:
    found = informal.detect(f"dime de q trata {text}")
    assert found is not None
    assert found.name in {"Inteligencia Artificial II", "Data Mining"}


def test_a_typo_never_turns_one_numeral_into_the_other(informal: SubjectIndex) -> None:
    found = informal.detect("inteligencia artificicial II")
    assert found is not None and found.name == "Inteligencia Artificial II"
    found = informal.detect("inteligencia artificicial I")
    assert found is not None and found.name == "Inteligencia Artificial I"
    assert (
        informal.detect("inteligencia artificial y la receta") is None
    )  # sin numeral: no se adivina


def test_fuzzy_matching_does_not_invent_subjects_from_common_words(informal: SubjectIndex) -> None:
    assert informal.detect("de que trata la receta de la paella") is None
    assert informal.detect("quiero un resumen de datos mineros") is None


@pytest.mark.parametrize(
    ("question", "kind", "subject", "topic"),
    [
        # las tres frases tal cual se escribieron
        (
            "dime de q trata la asignatura de inteligencia artificicial II sabes en un par de parrafos cuantos temas tiene todo",  # noqa: E501
            "overview_subject",
            "Inteligencia Artificial II",
            None,
        ),
        (
            "dime de q va el tema 5 de matematica discreta",
            "overview_topic",
            "Matemática Discreta",
            5,
        ),
        (
            "de q va la asignatura de sistemas operativos",
            "overview_subject",
            "Sistemas Operativos",
            None,
        ),
        # variantes informales
        ("q se da en ia 1", "overview_subject", "Inteligencia Artificial I", None),
        ("cuantos temas tiene data mining y de q va", "overview_subject", "Data Mining", None),
        ("resumeme la asignatura de redes pls", "overview_subject", "Redes", None),
        ("de que va el tema 4 de redes", "overview_topic", "Redes", 4),
        (
            "¿Qué temas tiene la asignatura de IA 2?",
            "overview_subject",
            "Inteligencia Artificial II",
            None,
        ),
        ("explicame la asignatura de data mining", "overview_subject", "Data Mining", None),
        (
            "cuántas unidades tiene inteligencia artificial 2",
            "overview_subject",
            "Inteligencia Artificial II",
            None,
        ),
        ("de qué va ssoo", "overview_subject", "Sistemas Operativos", None),
        ("que se da en el tema 5 de discretas", "overview_topic", "Matemática Discreta", 5),
        ("hablame de la materia de data mining", "overview_subject", "Data Mining", None),
        ("DE QUE TRATA DATA MINING??", "overview_subject", "Data Mining", None),
    ],
)
def test_informal_overview_questions_are_recognised(
    informal: SubjectIndex, question: str, kind: str, subject: str, topic: int | None
) -> None:
    index = informal
    intent = detect_intent(question, index)
    assert (intent.kind, intent.subject.name if intent.subject else None, intent.topic) == (
        kind,
        subject,
        topic,
    )


@pytest.mark.parametrize(
    "question",
    [
        "como se calcula la entropia en data mining",
        "¿Qué es una red neuronal en ia 2?",
        "diferencia entre proceso e hilo en sistemas operativos",
        "por que falla un semaforo en ssoo",
        "q es un grafo bipartito",
        "ejemplo de clustering en data mining",
    ],
)
def test_concrete_informal_questions_stay_normal_searches(
    informal: SubjectIndex, question: str
) -> None:
    assert detect_intent(question, informal).kind == "search"
