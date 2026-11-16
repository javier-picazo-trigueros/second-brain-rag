from __future__ import annotations

import hashlib
from pathlib import Path

from secondbrain.ingest.parser import parse_note

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
SEMAFOROS = "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md"
SIN_FM = "1º/IA/Sin frontmatter.md"
ENLACES = "1º/IA/Enlaces y embeds.md"
UTF16 = "2º/DIS/README.md"
CODIGO = "2º/DIS/Guia de scripts.md"
SIN_TEXTO = "3º/SISTEMAS/Temario cloud.md"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


# --- ruta, título y hash -------------------------------------------------------------------


def test_path_is_relative_posix_and_title_is_stem(vault: Path) -> None:
    note = parse_note(vault / CARRERA, vault)
    assert note.path == CARRERA
    assert note.title == "Condiciones de carrera"


def test_content_hash_is_sha256_of_raw_bytes(vault: Path) -> None:
    note = parse_note(vault / CARRERA, vault)
    assert note.content_hash == hashlib.sha256((vault / CARRERA).read_bytes()).hexdigest()


# --- frontmatter ---------------------------------------------------------------------------


def test_frontmatter_fields_are_extracted(vault: Path) -> None:
    note = parse_note(vault / CARRERA, vault)
    assert note.frontmatter["asignatura"] == "SISTEMAS OPERATIVOS"
    assert note.frontmatter["curso"] == "1º"
    assert note.frontmatter["conceptos_menores"] == ["exclusión mutua", "sección crítica"]


def test_body_excludes_frontmatter(vault: Path) -> None:
    note = parse_note(vault / CARRERA, vault)
    assert note.body.lstrip().startswith("# Condiciones de carrera")
    assert "asignatura:" not in note.body


def test_note_without_frontmatter_keeps_whole_body(vault: Path) -> None:
    note = parse_note(vault / SIN_FM, vault)
    assert note.frontmatter == {}
    assert note.body.startswith("# Regresión lineal")


def test_sin_texto_flag_is_preserved(vault: Path) -> None:
    assert parse_note(vault / SIN_TEXTO, vault).frontmatter["sin_texto"] is True


def test_invalid_yaml_is_dropped_but_body_survives(tmp_path: Path) -> None:
    _write(tmp_path, "rota.md", "---\nclave: [sin cerrar\n---\n\nCuerpo de la nota.\n")
    note = parse_note(tmp_path / "rota.md", tmp_path)
    assert note.frontmatter == {}
    assert note.body.strip() == "Cuerpo de la nota."


def test_non_mapping_yaml_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "lista.md", "---\n- uno\n- dos\n---\n\nCuerpo.\n")
    note = parse_note(tmp_path / "lista.md", tmp_path)
    assert note.frontmatter == {}
    assert note.body.strip() == "Cuerpo."


def test_crlf_frontmatter_is_parsed(tmp_path: Path) -> None:
    _write(tmp_path, "crlf.md", "---\r\nasignatura: IA\r\n---\r\nTexto\r\n")
    note = parse_note(tmp_path / "crlf.md", tmp_path)
    assert note.frontmatter == {"asignatura": "IA"}
    assert note.body.strip() == "Texto"


# --- codificación --------------------------------------------------------------------------


def test_utf16_note_is_decoded(vault: Path) -> None:
    note = parse_note(vault / UTF16, vault)
    assert note.title == "README"
    assert "Guía del proyecto DIS" in note.body
    assert "﻿" not in note.body


def test_utf8_bom_is_stripped(tmp_path: Path) -> None:
    (tmp_path / "bom.md").write_bytes(b"\xef\xbb\xbf# Titulo\n\nTexto\n")
    note = parse_note(tmp_path / "bom.md", tmp_path)
    assert note.body.startswith("# Titulo")


# --- tags ----------------------------------------------------------------------------------


def test_tags_merge_frontmatter_and_inline_without_duplicates(vault: Path) -> None:
    note = parse_note(vault / SEMAFOROS, vault)
    assert note.tags == ("concurrencia", "sincronizacion", "so/hilos", "exclusion-mutua")


def test_tags_ignore_code_blocks_and_inline_code(vault: Path) -> None:
    note = parse_note(vault / SEMAFOROS, vault)
    assert "include" not in note.tags
    assert "define" not in note.tags


def test_code_comments_are_not_tags(vault: Path) -> None:
    note = parse_note(vault / CODIGO, vault)
    assert note.tags == ("scripts",)


def test_tags_ignore_urls_anchors_and_headings(vault: Path) -> None:
    note = parse_note(vault / ENLACES, vault)
    assert "seccion" not in note.tags
    assert note.tags == ("enlaces", "enlaces-demo", "ia/busqueda")


def test_tags_are_lowercased_and_lose_leading_hash(tmp_path: Path) -> None:
    _write(tmp_path, "t.md", '---\ntags:\n  - "#Redes"\n  - IA\n---\n\nTexto #OtraEtiqueta\n')
    note = parse_note(tmp_path / "t.md", tmp_path)
    assert note.tags == ("redes", "ia", "otraetiqueta")


def test_scalar_tags_value_is_accepted(tmp_path: Path) -> None:
    _write(tmp_path, "t.md", "---\ntags: redes\n---\n\nTexto\n")
    assert parse_note(tmp_path / "t.md", tmp_path).tags == ("redes",)


# --- wikilinks -----------------------------------------------------------------------------


def test_links_from_body_and_frontmatter(vault: Path) -> None:
    note = parse_note(vault / SEMAFOROS, vault)
    assert note.links == ("Condiciones de carrera", "semaforo")


def test_links_handle_alias_anchor_block_path_and_dedupe(vault: Path) -> None:
    note = parse_note(vault / ENLACES, vault)
    assert note.links == (
        "Condiciones de carrera",
        "Semáforos y monitores",
        "Sin frontmatter",
        "semaforo",
        "firewall",
    )


def test_links_exclude_embeds_and_code(vault: Path) -> None:
    note = parse_note(vault / ENLACES, vault)
    assert "diagrama.png" not in note.links
    assert "no-es-un-enlace" not in note.links
    assert "tampoco-es-enlace" not in note.links


def test_original_field_is_not_a_link(vault: Path) -> None:
    note = parse_note(vault / CARRERA, vault)
    assert "Condiciones de carrera.pdf" not in note.links
    assert note.links == ("Semáforos y monitores", "condicion de carrera", "semaforo")


def test_links_to_non_note_files_are_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path, "n.md", "Ver [[informe.pdf]], [[foto.PNG]] y [[Python 3.11]] y [[otra nota]].\n"
    )
    note = parse_note(tmp_path / "n.md", tmp_path)
    assert note.links == ("Python 3.11", "otra nota")
