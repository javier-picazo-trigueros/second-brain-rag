from __future__ import annotations

import pytest

from secondbrain.answer.citations import CitationStream, validate_citations
from secondbrain.answer.context import Fragment


def frag(fid: str, title: str, path: str, page: int | None, kind: str = "evidence") -> Fragment:
    return Fragment(fid, title, path, title, kind, page, None)  # type: ignore[arg-type]


FRAGMENTS = [
    frag("S1", "Tema 5 Teoría de grafos [MD]", "3º/Discretas/Tema 5 Teoría de grafos [MD].md", 161),
    frag("S2", "Tema 5 Teoría de grafos [MD]", "3º/Discretas/Tema 5 Teoría de grafos [MD].md", 7),
    frag("S3", "Semáforos", "2º/SO/Semáforos.md", None),
    frag("S4", "Redes", "3º/Redes/Redes.md", None, kind="hint"),
]


def run(text: str) -> tuple[str, list[str], list[str]]:
    cleaned, report = validate_citations(text, FRAGMENTS)
    return cleaned, [c.id for c in report.citations], report.invalid


def test_a_valid_id_passes_through_unchanged() -> None:
    assert run("Un grafo es un par [S1].") == ("Un grafo es un par [S1].", ["S1"], [])


@pytest.mark.parametrize("raw", ["[S1, S3]", "[S1; S3]", "[S1 y S3]", "[ s1 , s3 ]", "[S1][S3]"])
def test_groups_are_normalised_to_one_bracket_per_id(raw: str) -> None:
    assert run(f"Dato {raw}.") == ("Dato [S1][S3].", ["S1", "S3"], [])


def test_an_id_the_model_invented_is_marked_and_reported() -> None:
    assert run("Dato [S9].") == ("Dato [cita no verificada: S9].", [], ["S9"])


def test_a_group_with_a_valid_and_an_invalid_id_keeps_the_valid_one() -> None:
    assert run("Dato [S1, S9].") == ("Dato [S1][cita no verificada: S9].", ["S1"], ["S9"])


def test_the_page_comes_from_the_fragment_so_a_page_the_model_adds_is_dropped() -> None:
    assert run("Dato [S1] (p. 161) y más.")[0] == "Dato [S1] y más."
    assert run("Dato [S1] (págs. 3-8).")[0] == "Dato [S1]."


def test_other_parentheses_after_a_citation_are_kept() -> None:
    assert run("Dato [S1] (ver arriba) y más.")[0] == "Dato [S1] (ver arriba) y más."


@pytest.mark.parametrize("text", ["array[0] = 1", "véase [1] y [nota]", "[x]", "a [ b ] c", "[]"])
def test_brackets_that_are_not_citations_are_untouched(text: str) -> None:
    assert run(text) == (text, [], [])


def test_a_title_in_double_brackets_is_an_unverified_citation() -> None:
    cleaned, ids, invalid = run("Dato [[Tema 5 Teoría de grafos [MD]]] y más.")
    assert cleaned == "Dato [cita no verificada: Tema 5 Teoría de grafos [MD]] y más."
    assert ids == [] and invalid == ["Tema 5 Teoría de grafos [MD]"]


def test_citations_are_unique_and_in_order_of_appearance() -> None:
    assert run("[S3] y [S1] y [S3] y [S1]")[1] == ["S3", "S1"]


def test_citation_carries_the_fragment_data() -> None:
    _, report = validate_citations("Dato [S2].", FRAGMENTS)
    (citation,) = report.citations
    assert (citation.path, citation.page, citation.kind) == (
        "3º/Discretas/Tema 5 Teoría de grafos [MD].md",
        7,
        "evidence",
    )


def test_only_hints_is_true_when_every_citation_is_a_hint() -> None:
    assert validate_citations("Ver [S4].", FRAGMENTS)[1].only_hints is True
    assert validate_citations("Ver [S4] y [S3].", FRAGMENTS)[1].only_hints is False
    assert validate_citations("Sin citas.", FRAGMENTS)[1].only_hints is False


@pytest.mark.parametrize(
    "text",
    [
        "Un grafo [S1] (p. 161) y un semáforo [S3, S9]. Ver [[Inventada]] [x] [S4].",
        "Texto largo sin citas ni corchetes.",
        "Dato [S1] (ver arriba)",
        "Termina con un corchete [",
    ],
)
def test_streaming_by_characters_gives_the_same_text_and_report(text: str) -> None:
    expected, expected_report = validate_citations(text, FRAGMENTS)
    stream = CitationStream(FRAGMENTS)
    out = "".join(stream.feed(ch) for ch in text) + stream.finish()
    assert out == expected
    assert stream.report.invalid == expected_report.invalid
    assert [c.id for c in stream.report.citations] == [c.id for c in expected_report.citations]


def test_an_unverified_id_is_never_emitted_while_streaming() -> None:
    stream = CitationStream(FRAGMENTS)
    emitted = ""
    for piece in ["Dato [", "S", "9", "]", " fin"]:
        emitted += stream.feed(piece)
        assert "[S9" not in emitted
    emitted += stream.finish()
    assert emitted == "Dato [cita no verificada: S9] fin"


def test_a_citation_waits_for_a_possible_page_suffix_but_finish_flushes_it() -> None:
    stream = CitationStream(FRAGMENTS)
    assert stream.feed("Dato [S1]") == "Dato "  # espera por si llega "(p. N)"
    assert stream.finish() == "[S1]"
