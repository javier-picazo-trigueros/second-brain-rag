from __future__ import annotations

import pytest

from secondbrain.answer.citations import CitationStream, validate_citations
from secondbrain.answer.context import Source


def src(
    label: str, path: str, pages: tuple[int, ...] = (), kind: str = "evidence", title: str = ""
) -> Source:
    return Source(
        label=label,
        path=path,
        title=title or label.rsplit("/", 1)[-1],
        kind=kind,  # type: ignore[arg-type]
        pages=pages,
        asignatura=None,
        curso=None,
    )


SOURCES = [
    src("Semáforos", "1º/SO/Semáforos.md", (7, 9)),
    src("OpenMP", "2º/CAR/OpenMP.md", ()),
    src("Redes", "3º/Redes.md", (), kind="hint"),
]


# --- validación sobre texto completo ------------------------------------------------------------


def test_a_valid_citation_with_a_valid_page_is_left_untouched() -> None:
    text, report = validate_citations("Un semáforo cuenta [[Semáforos]] (p. 7).", SOURCES)
    assert text == "Un semáforo cuenta [[Semáforos]] (p. 7)."
    assert [(c.path, c.page) for c in report.citations] == [("1º/SO/Semáforos.md", 7)]
    assert report.invalid == [] and report.bad_pages == []


def test_a_citation_without_page_is_valid() -> None:
    text, report = validate_citations("Se usa [[Semáforos]].", SOURCES)
    assert text == "Se usa [[Semáforos]]."
    assert report.citations[0].page is None


def test_an_unknown_note_is_marked_as_unverified() -> None:
    text, report = validate_citations("Dato [[Inventada]] aquí.", SOURCES)
    assert text == "Dato [cita no verificada: Inventada] aquí."
    assert report.invalid == ["Inventada"]
    assert report.citations == []


def test_alias_and_anchor_are_dropped_and_the_label_is_canonical() -> None:
    text, _ = validate_citations("[[Semáforos|el apunte]] y [[semáforos#Monitores]]", SOURCES)
    assert text == "[[Semáforos]] y [[Semáforos]]"


def test_matching_ignores_case_and_the_md_extension() -> None:
    text, report = validate_citations("[[SEMÁFOROS]] [[1º/SO/Semáforos.md]]", SOURCES)
    assert text == "[[Semáforos]] [[Semáforos]]"
    assert report.invalid == []


def test_a_page_that_is_not_in_the_context_is_flagged() -> None:
    text, report = validate_citations("Cuenta [[Semáforos]] (p. 99).", SOURCES)
    assert text == "Cuenta [[Semáforos]] (p. 99 no verificada)."
    assert report.bad_pages == [("1º/SO/Semáforos.md", 99)]
    assert report.citations[0].page is None


def test_a_page_for_a_note_without_page_information_is_flagged() -> None:
    text, report = validate_citations("[[OpenMP]] (p. 3)", SOURCES)
    assert text == "[[OpenMP]] (p. 3 no verificada)"
    assert report.bad_pages == [("2º/CAR/OpenMP.md", 3)]


def test_page_formats_are_recognised() -> None:
    text, report = validate_citations("[[Semáforos]](p.7) y [[Semáforos]] (pág. 9)", SOURCES)
    assert text == "[[Semáforos]](p.7) y [[Semáforos]] (pág. 9)"
    assert [c.page for c in report.citations] == [7, 9]


def test_repeated_citations_are_reported_once_in_order() -> None:
    _, report = validate_citations("[[OpenMP]] [[Semáforos]] [[OpenMP]]", SOURCES)
    assert [c.label for c in report.citations] == ["OpenMP", "Semáforos"]


def test_related_hints_count_as_part_of_the_context_but_are_reported_as_such() -> None:
    _, report = validate_citations("Ver también [[Redes]].", SOURCES)
    assert report.invalid == []
    assert report.citations[0].kind == "hint"
    assert report.only_hints is True


def test_citing_evidence_and_hints_is_not_only_hints() -> None:
    _, report = validate_citations("[[Semáforos]] y ver [[Redes]]", SOURCES)
    assert report.only_hints is False


def test_no_citations_means_not_only_hints() -> None:
    _, report = validate_citations("Sin citas.", SOURCES)
    assert (report.citations, report.only_hints) == ([], False)


def test_ambiguous_titles_are_not_guessed() -> None:
    sources = [src("1º/IA/Apuntes", "1º/IA/Apuntes.md"), src("2º/IA/Apuntes", "2º/IA/Apuntes.md")]
    text, report = validate_citations("[[Apuntes]] pero [[2º/IA/Apuntes]]", sources)
    assert text == "[cita no verificada: Apuntes] pero [[2º/IA/Apuntes]]"
    assert report.invalid == ["Apuntes"]


def test_text_without_brackets_is_unchanged() -> None:
    text, _ = validate_citations("Nada [raro] (p. 3) aquí", SOURCES)
    assert text == "Nada [raro] (p. 3) aquí"


# --- streaming --------------------------------------------------------------------------------

SAMPLES = [
    "Un semáforo cuenta [[Semáforos]] (p. 7). Además [[Inventada]] y [[OpenMP]].",
    "Alias [[Semáforos|apunte]] y ancla [[Semáforos#Monitores]](p.9) fin",
    "Página mala [[Semáforos]] (p. 99) y otra [[OpenMP]] (p. 2) y texto (p. 5) suelto",
    "Corchetes sueltos [uno] y [[ y ]] y [[sin cerrar\nsalto de línea [[Semáforos]]",
    "Termina con cita [[Semáforos]]",
    "Termina con página [[Semáforos]] (p. 7",
    "Termina abierta [[Semáfo",
    "Termina con corchete [",
    "Acentos y ñ [[Redes]] — ¿qué? (ver más)",
]


@pytest.mark.parametrize("sample", SAMPLES)
@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 13, 1000])
def test_streaming_gives_the_same_result_as_validating_the_whole_text(
    sample: str, size: int
) -> None:
    expected, expected_report = validate_citations(sample, SOURCES)
    stream = CitationStream(SOURCES)
    pieces = [stream.feed(sample[i : i + size]) for i in range(0, len(sample), size)]
    pieces.append(stream.finish())
    assert "".join(pieces) == expected
    assert stream.report.invalid == expected_report.invalid
    assert stream.report.bad_pages == expected_report.bad_pages
    assert [(c.path, c.page) for c in stream.report.citations] == [
        (c.path, c.page) for c in expected_report.citations
    ]


@pytest.mark.parametrize("size", [1, 2, 3, 7])
def test_the_client_never_sees_an_unverified_citation_even_mid_stream(size: int) -> None:
    text = "Dato [[Inventada]] y [[Otra cosa]] y [[Semáforos]] (p. 7)."
    stream = CitationStream(SOURCES)
    seen = ""
    for i in range(0, len(text), size):
        seen += stream.feed(text[i : i + size])
        assert "[[Inventada" not in seen and "[[Otra" not in seen
    seen += stream.finish()
    assert "[[Inventada" not in seen and "[cita no verificada: Inventada]" in seen


def test_normal_text_is_not_held_back() -> None:
    stream = CitationStream(SOURCES)
    assert stream.feed("Hola mundo, esto fluye") == "Hola mundo, esto fluye"


def test_only_a_possible_citation_start_is_held_back() -> None:
    stream = CitationStream(SOURCES)
    assert stream.feed("Texto [") == "Texto "
    assert stream.feed("x] sigue") == "[x] sigue"


def test_a_citation_split_across_tokens_is_validated_as_a_whole() -> None:
    stream = CitationStream(SOURCES)
    out = (
        stream.feed("Mira [[Sem")
        + stream.feed("áforos]]")
        + stream.feed(" y listo")
        + stream.finish()
    )
    assert out == "Mira [[Semáforos]] y listo"


def test_a_page_suffix_split_across_tokens_is_validated() -> None:
    stream = CitationStream(SOURCES)
    out = ""
    for piece in ("[[Semáforos]]", " (", "p", ". ", "99", ")", " fin"):
        out += stream.feed(piece)
    out += stream.finish()
    assert out == "[[Semáforos]] (p. 99 no verificada) fin"


def test_a_very_long_unclosed_bracket_is_released() -> None:
    stream = CitationStream(SOURCES)
    out = stream.feed("[[" + "a" * 400) + stream.finish()
    assert out == "[[" + "a" * 400


@pytest.mark.parametrize("size", [1, 7, 1000])
def test_a_closed_bracket_longer_than_any_title_is_plain_text(size: int) -> None:
    text = "antes [[" + "a" * 300 + "]] después"
    stream = CitationStream(SOURCES)
    out = "".join(stream.feed(text[i : i + size]) for i in range(0, len(text), size))
    out += stream.finish()
    assert out == text
    assert stream.report.invalid == []


# --- páginas con paréntesis intermedios, rangos y listas (visto en respuestas reales) ---


def test_a_parenthetical_between_the_citation_and_the_page_is_kept_and_the_page_checked() -> None:
    text, report = validate_citations("Cuenta [[Semáforos]] (EDA, 3º) (p. 7).", SOURCES)
    assert text == "Cuenta [[Semáforos]] (EDA, 3º) (p. 7)."
    assert [(c.path, c.page) for c in report.citations] == [("1º/SO/Semáforos.md", 7)]


def test_a_wrong_page_after_a_parenthetical_is_flagged() -> None:
    text, report = validate_citations("Cuenta [[Semáforos]] (EDA, 3º) (p. 99).", SOURCES)
    assert text == "Cuenta [[Semáforos]] (EDA, 3º) (p. 99 no verificada)."
    assert report.bad_pages == [("1º/SO/Semáforos.md", 99)]


@pytest.mark.parametrize(
    "expression", ["(p. 7-9)", "(pp. 7, 9)", "(págs. 7 y 9)", "(p. 7\u20139)", "(p.7;9)"]
)
def test_ranges_and_lists_of_known_pages_are_accepted(expression: str) -> None:
    text, report = validate_citations(f"[[Semáforos]] {expression}", SOURCES)
    assert text == f"[[Semáforos]] {expression}"
    assert report.bad_pages == [] and report.citations[0].page == 7


@pytest.mark.parametrize(
    ("expression", "shown", "bad"),
    [("(p. 7-8)", "7-8", [8]), ("(pp. 3, 7)", "3, 7", [3]), ("(p. 2-3)", "2-3", [2, 3])],
)
def test_a_range_or_list_with_an_unknown_page_is_flagged(
    expression: str, shown: str, bad: list[int]
) -> None:
    text, report = validate_citations(f"[[Semáforos]] {expression}", SOURCES)
    assert text == f"[[Semáforos]] (p. {shown} no verificada)"
    assert [page for _, page in report.bad_pages] == bad
    assert report.citations[0].page is None or report.citations[0].page in (7, 9)


def test_unrelated_parentheses_after_a_citation_are_left_alone() -> None:
    text, report = validate_citations("[[Semáforos]] (ver más) y algo (p. 5) suelto", SOURCES)
    assert text == "[[Semáforos]] (ver más) y algo (p. 5) suelto"
    assert report.bad_pages == []


def test_a_long_parenthetical_is_not_treated_as_a_decoration() -> None:
    long = "(" + "x" * 60 + ")"
    text, report = validate_citations(f"[[Semáforos]] {long} (p. 99)", SOURCES)
    assert text == f"[[Semáforos]] {long} (p. 99)"  # la página no está pegada a la cita
    assert report.bad_pages == []


PAGE_SAMPLES = [
    "Cuenta [[Semáforos]] (EDA, 3º) (p. 7) y [[OpenMP]] (Alto rendimiento, 4º) (p. 3).",
    "Rango [[Semáforos]] (p. 7-9) y lista [[Semáforos]] (pp. 7, 99) y [[Semáforos]] (p. 2-3).",
    "Termina con paréntesis [[Semáforos]] (EDA, 3º)",
    "Termina a medias [[Semáforos]] (EDA, 3º) (p. 7",
    "Dos decoraciones [[Semáforos]] (a) (b) (p. 7)",
]


@pytest.mark.parametrize("sample", PAGE_SAMPLES)
@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 1000])
def test_streaming_matches_the_full_validation_for_page_expressions(sample: str, size: int) -> None:
    expected, expected_report = validate_citations(sample, SOURCES)
    stream = CitationStream(SOURCES)
    pieces = [stream.feed(sample[i : i + size]) for i in range(0, len(sample), size)]
    pieces.append(stream.finish())
    assert "".join(pieces) == expected
    assert stream.report.bad_pages == expected_report.bad_pages
    assert [(c.path, c.page) for c in stream.report.citations] == [
        (c.path, c.page) for c in expected_report.citations
    ]
