from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
import yaml

from secondbrain.config import Settings
from secondbrain.generated import (
    GENERATED_DIR,
    MAX_BYTES,
    GeneratedError,
    build_note,
    preview,
    safe_name,
    save,
)


def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, vault_path=tmp_path)  # type: ignore[call-arg]


# --- el índice no debe leer lo generado --------------------------------------------------


def test_the_generated_folder_is_never_indexed(tmp_path: Path) -> None:
    s = settings(tmp_path)
    assert s.is_excluded(f"{GENERATED_DIR}/Apuntes tema 5.md")
    assert s.is_excluded(f"3º/Discretas/{GENERATED_DIR}/x.md")
    assert not s.is_excluded("3º/Discretas/Tema 5.md")


# --- nombre del fichero ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Apuntes del tema 5 de Matemática Discreta", "Apuntes del tema 5 de Matemática Discreta"),
        ("../../etc/passwd", "etc passwd"),
        ('a/b\\c:d*e?f"g<h>i|j', "a b c d e f g h i j"),
        ("Tema [MD] #5 ^x", "Tema MD 5 x"),
        ("  con  espacios   y puntos...  ", "con espacios y puntos"),
        ("", "Apuntes"),
        ("...", "Apuntes"),
        ("CON", "CON apuntes"),  # nombre reservado de Windows
        ("nul.txt", "nul txt"),
        ("x" * 300, "x" * 80),
    ],
)
def test_safe_name(title: str, expected: str) -> None:
    assert safe_name(title) == expected


# --- contenido ---------------------------------------------------------------------------


def note(**over: object) -> str:
    args: dict[str, object] = {
        "title": "Apuntes del tema 5",
        "markdown": "## Grafos\n\nUn grafo es un par $G=(V,E)$ [S1].",
        "asignatura": "Matemática Discreta",
        "tema": 5,
        "sources": ["3º/Discretas/Tema 5 Ejemplo de grafos [MD].md", "3º/Discretas/Resumen.md"],
        "today": date(2026, 11, 17),
    }
    args.update(over)
    return build_note(**args)  # type: ignore[arg-type]


def frontmatter(text: str) -> dict[str, object]:
    assert text.startswith("---\n")
    head = text.split("\n---\n", 1)[0].removeprefix("---\n")
    loaded = yaml.safe_load(head)
    assert isinstance(loaded, dict)
    return loaded


def test_the_note_has_frontmatter_with_subject_topic_date_and_sources() -> None:
    meta = frontmatter(note())
    assert meta["asignatura"] == "Matemática Discreta"
    assert meta["tema"] == 5
    assert str(meta["fecha"]) == "2026-11-17"
    assert meta["generada"] is True
    assert len(meta["fuentes"]) == 2  # type: ignore[arg-type]


def test_sources_are_wikilinks_when_the_title_allows_it_and_markdown_links_otherwise() -> None:
    meta = frontmatter(note())
    fuentes = meta["fuentes"]
    assert fuentes[1] == "[[Resumen]]"  # type: ignore[index]
    # «[MD]» no cabe en un [[enlace]] de Obsidian: enlace Markdown con la ruta codificada
    assert fuentes[0].startswith("[Tema 5 Ejemplo de grafos \\[MD\\]](")  # type: ignore[index]
    assert "3%C2%BA/Discretas/Tema%205%20Ejemplo%20de%20grafos%20%5BMD%5D.md" in fuentes[0]  # type: ignore[index]


def test_the_body_keeps_the_markdown_and_lists_the_sources_at_the_end() -> None:
    text = note()
    body = text.split("\n---\n", 1)[1]
    assert "## Grafos" in body and "$G=(V,E)$" in body
    assert body.rstrip().splitlines()[-1].startswith("- ")
    assert "## Fuentes" in body


def test_citation_ids_are_not_left_in_the_saved_note() -> None:
    body = note().split("\n---\n", 1)[1]
    assert "[S1]" not in body


def test_hostile_text_cannot_break_out_of_the_frontmatter() -> None:
    text = note(asignatura="X\n---\nmalo: true", sources=['a"b\n---\n.md'])
    meta = frontmatter(text)
    assert "malo" not in meta
    assert meta["asignatura"] == "X --- malo: true"


# --- vista previa y guardado -------------------------------------------------------------


def test_preview_returns_the_exact_relative_path_and_content(tmp_path: Path) -> None:
    p = preview(settings(tmp_path), "Apuntes del tema 5", note())
    assert p.path == f"{GENERATED_DIR}/Apuntes del tema 5.md"
    assert p.content == note()
    assert not (tmp_path / GENERATED_DIR).exists()  # la vista previa no escribe nada


def test_preview_proposes_a_free_name_when_the_file_exists(tmp_path: Path) -> None:
    s = settings(tmp_path)
    (tmp_path / GENERATED_DIR).mkdir()
    (tmp_path / GENERATED_DIR / "Apuntes.md").write_text("mío", encoding="utf-8")
    (tmp_path / GENERATED_DIR / "Apuntes (2).md").write_text("mío", encoding="utf-8")
    assert preview(s, "Apuntes", "x").path == f"{GENERATED_DIR}/Apuntes (3).md"


def test_save_writes_only_inside_the_generated_folder_and_creates_it(tmp_path: Path) -> None:
    s = settings(tmp_path)
    final = save(s, f"{GENERATED_DIR}/Apuntes.md", "contenido")
    assert final == f"{GENERATED_DIR}/Apuntes.md"
    assert (tmp_path / GENERATED_DIR / "Apuntes.md").read_text(encoding="utf-8") == "contenido"
    assert [p.name for p in tmp_path.iterdir()] == [GENERATED_DIR]


def test_save_never_overwrites_it_adds_a_suffix(tmp_path: Path) -> None:
    s = settings(tmp_path)
    (tmp_path / GENERATED_DIR).mkdir()
    original = tmp_path / GENERATED_DIR / "Apuntes.md"
    original.write_text("de otra persona", encoding="utf-8")
    final = save(s, f"{GENERATED_DIR}/Apuntes.md", "nuevo")
    assert final == f"{GENERATED_DIR}/Apuntes (2).md"
    assert original.read_text(encoding="utf-8") == "de otra persona"
    again = save(s, f"{GENERATED_DIR}/Apuntes.md", "otro")
    assert again == f"{GENERATED_DIR}/Apuntes (3).md"


@pytest.mark.parametrize(
    "path",
    [
        "Apuntes.md",  # fuera de _generadas
        "../Apuntes.md",
        f"{GENERATED_DIR}/../Fuera.md",
        f"{GENERATED_DIR}/sub/Apuntes.md",  # nada de subcarpetas
        "/etc/Apuntes.md",
        "C:/Windows/Apuntes.md",
        f"{GENERATED_DIR}/Apuntes.txt",  # solo .md
        f"{GENERATED_DIR}\\..\\Fuera.md",
        f"{GENERATED_DIR}/",
        "",
    ],
)
def test_save_rejects_paths_outside_the_generated_folder(tmp_path: Path, path: str) -> None:
    with pytest.raises(GeneratedError):
        save(settings(tmp_path), path, "x")
    assert list(tmp_path.iterdir()) == []


def test_save_rejects_empty_or_huge_content(tmp_path: Path) -> None:
    s = settings(tmp_path)
    with pytest.raises(GeneratedError):
        save(s, f"{GENERATED_DIR}/A.md", "   ")
    with pytest.raises(GeneratedError):
        save(s, f"{GENERATED_DIR}/A.md", "x" * (MAX_BYTES + 1))


def test_save_refuses_when_the_vault_does_not_exist(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    s = settings(vault)
    vault.rmdir()
    with pytest.raises(GeneratedError):
        save(s, f"{GENERATED_DIR}/A.md", "x")
    assert not vault.exists()


@pytest.mark.skipif(os.name == "nt", reason="los symlinks piden permisos especiales en Windows")
def test_save_refuses_a_generated_folder_that_points_outside_the_vault(tmp_path: Path) -> None:
    outside = tmp_path / "fuera"
    outside.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / GENERATED_DIR).symlink_to(outside, target_is_directory=True)
    with pytest.raises(GeneratedError):
        save(settings(vault), f"{GENERATED_DIR}/A.md", "x")
    assert list(outside.iterdir()) == []


def test_content_is_written_as_utf8_with_unix_newlines(tmp_path: Path) -> None:
    save(settings(tmp_path), f"{GENERATED_DIR}/A.md", "ñ\n$x$\n")
    assert (tmp_path / GENERATED_DIR / "A.md").read_bytes() == "ñ\n$x$\n".encode()
