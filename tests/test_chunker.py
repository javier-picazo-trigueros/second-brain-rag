from __future__ import annotations

from pathlib import Path
from typing import Any

from secondbrain.domain import ParsedNote
from secondbrain.ingest.chunker import chunk_note
from secondbrain.ingest.parser import parse_note


def _note(body: str, path: str = "a/n.md", **fm: Any) -> ParsedNote:
    return ParsedNote(path, "n", dict(fm), ("t1",), ("L1",), body, "h")


def _para(label: str, n: int = 80) -> str:
    return f"{label} " + "palabra " * n


# --- jerarquía de encabezados ---------------------------------------------------------------


def test_heading_path_follows_hierarchy() -> None:
    body = f"# A\n\n{_para('a')}\n\n## B\n\n{_para('b')}\n\n### C\n\n{_para('c')}\n"
    paths = [c.heading_path for c in chunk_note(_note(body), max_chars=1800, min_chars=10)]
    assert paths == [("A",), ("A", "B"), ("A", "B", "C")]


def test_sibling_heading_replaces_previous_sibling() -> None:
    body = f"# A\n\n## B\n\n{_para('b')}\n\n## C\n\n{_para('c')}\n"
    paths = [c.heading_path for c in chunk_note(_note(body), min_chars=10)]
    assert paths == [("A", "B"), ("A", "C")]


def test_note_without_headings_has_empty_heading_path() -> None:
    chunks = chunk_note(_note(_para("solo texto")), min_chars=10)
    assert [c.heading_path for c in chunks] == [()]


# --- código ---------------------------------------------------------------------------------


def test_hash_inside_fence_is_not_a_heading() -> None:
    body = f"# A\n\n{_para('x')}\n\n## B\n\n```python\n# no es encabezado\nprint(1)\n```\n"
    chunks = chunk_note(_note(body), max_chars=400, min_chars=10)
    assert any(c.heading_path == ("A", "B") and "print(1)" in c.text for c in chunks)
    assert not any(c.heading_path and c.heading_path[-1] == "no es encabezado" for c in chunks)


def test_code_block_with_blank_lines_is_atomic() -> None:
    code = "```python\na = 1\n\n\nb = 2\n```"
    body = f"# T\n\n{_para('intro', 20)}\n\n{code}\n\n{_para('fin', 20)}\n"
    chunks = chunk_note(_note(body), max_chars=400, min_chars=10)
    assert sum(code in c.text for c in chunks) == 1


def test_real_fixture_ignores_hashes_in_fences(vault: Path) -> None:
    note = parse_note(vault / "2º/DIS/Guia de scripts.md", vault)
    chunks = chunk_note(note, max_chars=1800, min_chars=10)
    headings = {h for c in chunks for h in c.heading_path}
    assert "Lee la configuración" not in headings
    assert "esto tampoco es un encabezado" not in headings
    assert any("# Construye y levanta los contenedores" in c.text for c in chunks)
    assert any("# otro comentario dentro de un bloque con tildes" in c.text for c in chunks)


# --- tamaño ---------------------------------------------------------------------------------


def test_chunks_respect_max_chars() -> None:
    body = "# T\n\n" + "\n\n".join(_para(f"p{i}", 40) for i in range(12))
    chunks = chunk_note(_note(body), max_chars=800, min_chars=100)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 for c in chunks)


def test_single_overlong_line_is_hard_split() -> None:
    chunks = chunk_note(_note("x" * 5000), max_chars=1000, min_chars=100)
    assert len(chunks) == 5
    assert all(len(c.text) <= 1000 for c in chunks)


def test_small_pieces_are_merged_with_previous() -> None:
    body = f"## A\n\n{'a' * 80}\n\n## B\n\n{'b' * 80}\n"
    chunks = chunk_note(_note(body), max_chars=1800, min_chars=300)
    assert len(chunks) == 1
    assert "**B**" in chunks[0].text
    assert "a" * 80 in chunks[0].text and "b" * 80 in chunks[0].text


def test_tiny_pieces_are_dropped() -> None:
    assert chunk_note(_note("# T\n\ncorto"), min_chars=10) == []


# --- placeholders y sin_texto ---------------------------------------------------------------


def test_placeholder_only_note_produces_no_chunks(vault: Path) -> None:
    note = parse_note(vault / "3º/SISTEMAS/Temario cloud.md", vault)
    assert chunk_note(note) == []


def test_placeholders_are_removed_from_text() -> None:
    body = f"# T\n\n{_para('real')}\n\n*(sin texto extraíble: ver PDF)*\n"
    chunks = chunk_note(_note(body), min_chars=10)
    assert chunks
    assert all("sin texto extraíble" not in c.text for c in chunks)


# --- páginas --------------------------------------------------------------------------------


def test_page_headings_are_not_part_of_heading_path(vault: Path) -> None:
    note = parse_note(vault / "1º/IA/Apuntes con paginas vacias.md", vault)
    chunks = chunk_note(note, max_chars=1800, min_chars=50)
    assert [c.heading_path for c in chunks] == [
        ("Búsqueda en anchura",),
        ("Búsqueda en profundidad",),
    ]
    assert all("Página" not in c.text for c in chunks)


def test_chunk_records_page_number(vault: Path) -> None:
    note = parse_note(vault / "1º/IA/Apuntes con paginas vacias.md", vault)
    chunks = chunk_note(note, max_chars=1800, min_chars=50)
    assert [c.page for c in chunks] == [1, 3]


def test_page_is_none_without_page_markers() -> None:
    chunks = chunk_note(_note(f"# A\n\n{_para('a')}"), min_chars=10)
    assert [c.page for c in chunks] == [None]


def test_section_spanning_pages_keeps_heading_and_splits_by_page() -> None:
    body = f"## Página 1\n\n# Tema\n\n{_para('uno')}\n\n## Página 2\n\n{_para('dos')}\n"
    chunks = chunk_note(_note(body), min_chars=10)
    assert [(c.heading_path, c.page) for c in chunks] == [(("Tema",), 1), (("Tema",), 2)]


# --- ids, posiciones y metadatos ------------------------------------------------------------


def test_ids_are_deterministic_and_unique() -> None:
    body = f"# A\n\n{_para('a')}\n\n## B\n\n{_para('b')}\n"
    first = chunk_note(_note(body), min_chars=10)
    again = chunk_note(_note(body), min_chars=10)
    assert [c.id for c in first] == [c.id for c in again]
    assert len({c.id for c in first}) == len(first)


def test_ids_depend_on_note_path() -> None:
    body = f"# A\n\n{_para('a')}\n"
    a = chunk_note(_note(body, path="x.md"), min_chars=10)
    b = chunk_note(_note(body, path="y.md"), min_chars=10)
    assert a[0].id != b[0].id


def test_positions_are_consecutive_from_zero() -> None:
    body = "\n\n".join(f"## S{i}\n\n{_para(f's{i}')}" for i in range(4))
    chunks = chunk_note(_note(body), min_chars=10)
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_metadata_is_propagated_from_note() -> None:
    note = _note(f"# A\n\n{_para('a')}", asignatura="IA", curso="2º", resumen="Resumen")
    c = chunk_note(note, min_chars=10)[0]
    assert (c.note_path, c.note_title) == ("a/n.md", "n")
    assert (c.asignatura, c.curso, c.resumen) == ("IA", "2º", "Resumen")
    assert c.tags == ("t1",) and c.links == ("L1",)


def test_missing_metadata_is_none() -> None:
    c = chunk_note(_note(f"# A\n\n{_para('a')}"), min_chars=10)[0]
    assert (c.asignatura, c.curso, c.resumen) == (None, None, None)


def test_embed_text_prefixes_title_and_heading_path() -> None:
    body = f"# A\n\n## B\n\n{_para('b')}"
    c = chunk_note(_note(body), min_chars=10)[0]
    assert c.embed_text.startswith("n > A > B\n\n")
    assert c.embed_text.endswith(c.text)


def test_long_multiline_block_is_split_on_line_boundaries() -> None:
    lines = [f"linea {i} " + "x" * 290 for i in range(10)]
    chunks = chunk_note(_note("\n".join(lines)), max_chars=700, min_chars=100)
    assert len(chunks) > 1
    assert all(len(c.text) <= 700 for c in chunks)
    assert "\n".join(c.text for c in chunks).split("\n") == lines
