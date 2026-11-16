from __future__ import annotations

from secondbrain.notes import resolve_note

PATHS = {
    "1º/IA/Apuntes.md",
    "2º/IA/Apuntes.md",
    "1º/SO/Condiciones de carrera.md",
    "3º/Redes/Network layers.md",
}


def test_an_exact_path_wins() -> None:
    assert resolve_note(PATHS, "1º/IA/Apuntes.md") == ["1º/IA/Apuntes.md"]


def test_a_unique_title_resolves_to_its_path() -> None:
    assert resolve_note(PATHS, "Network layers") == ["3º/Redes/Network layers.md"]


def test_titles_ignore_case() -> None:
    assert resolve_note(PATHS, "condiciones DE carrera") == ["1º/SO/Condiciones de carrera.md"]


def test_a_repeated_title_returns_every_candidate_sorted() -> None:
    assert resolve_note(PATHS, "Apuntes") == ["1º/IA/Apuntes.md", "2º/IA/Apuntes.md"]


def test_the_md_extension_is_optional_in_a_path() -> None:
    assert resolve_note(PATHS, "1º/SO/Condiciones de carrera") == [
        "1º/SO/Condiciones de carrera.md"
    ]


def test_unknown_notes_resolve_to_nothing() -> None:
    assert resolve_note(PATHS, "no existe") == []


def test_surrounding_whitespace_is_ignored() -> None:
    assert resolve_note(PATHS, "  Network layers \n") == ["3º/Redes/Network layers.md"]
