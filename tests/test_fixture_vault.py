"""Comprueba que el vault de ejemplo cubre los casos que necesitan los tests de la Fase 1."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CONTENT_NOTES = {
    "frontmatter_completo": "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md",
    "wikilinks_embeds_tags": "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md",
    "sin_frontmatter": "1º/IA/Sin frontmatter.md",
    "utf16": "2º/DIS/README.md",
    "codigo_con_almohadillas": "2º/DIS/Guia de scripts.md",
    "sin_texto": "3º/SISTEMAS/Temario cloud.md",
    "termino_exacto": "4º/Seguridad/Cortafuegos con iptables.md",
    "ingles": "3º/REDES/Network layers.md",
    "placeholders": "1º/IA/Apuntes con paginas vacias.md",
    "enlaces_variantes": "1º/IA/Enlaces y embeds.md",
}
CONCEPT_NOTES = [
    "_conceptos/condicion de carrera.md",
    "_conceptos/semaforo.md",
    "_conceptos/firewall.md",
]
# Ficheros que el indexador debe ignorar (carpetas excluidas, ficheros excluidos, no-.md).
EXCLUDED = [
    "CLAUDE.md",
    "_INDICE.md",
    ".obsidian/workspace.md",
    "_archivo/Nota vieja.md",
    "node_modules/paquete/README.md",
    "convertir.py",
]


def test_vault_has_between_8_and_10_content_notes(vault: Path) -> None:
    assert 8 <= len(CONTENT_NOTES) <= 10
    for rel in CONTENT_NOTES.values():
        assert (vault / rel).is_file(), rel


@pytest.mark.parametrize("rel", CONCEPT_NOTES)
def test_concept_notes_exist(vault: Path, rel: str) -> None:
    assert (vault / rel).is_file()


@pytest.mark.parametrize("rel", EXCLUDED)
def test_excluded_decoys_exist(vault: Path, rel: str) -> None:
    assert (vault / rel).is_file()


def test_utf16_note_is_really_utf16(vault: Path) -> None:
    raw = (vault / CONTENT_NOTES["utf16"]).read_bytes()
    assert raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    assert "README" in raw.decode("utf-16") or "Guía" in raw.decode("utf-16")


def test_note_without_frontmatter_has_none(vault: Path) -> None:
    assert (
        not (vault / CONTENT_NOTES["sin_frontmatter"]).read_text(encoding="utf-8").startswith("---")
    )


def test_sin_texto_note_is_flagged_and_has_placeholder(vault: Path) -> None:
    text = (vault / CONTENT_NOTES["sin_texto"]).read_text(encoding="utf-8")
    assert "sin_texto: true" in text
    assert "*(sin texto extraíble: ver PDF)*" in text


def test_code_note_has_hash_inside_fences(vault: Path) -> None:
    text = (vault / CONTENT_NOTES["codigo_con_almohadillas"]).read_text(encoding="utf-8")
    assert "```" in text
    assert "~~~" in text
    assert "\n# " in text


def test_links_note_covers_alias_anchor_and_embed(vault: Path) -> None:
    text = (vault / CONTENT_NOTES["enlaces_variantes"]).read_text(encoding="utf-8")
    assert re.search(r"(?<!!)\[\[[^\]|]+\|[^\]]+\]\]", text)  # alias
    assert re.search(r"(?<!!)\[\[[^\]|]+#[^\]]+\]\]", text)  # ancla
    assert "![[" in text  # embed


def test_english_note_is_english(vault: Path) -> None:
    text = (vault / CONTENT_NOTES["ingles"]).read_text(encoding="utf-8")
    assert "the" in text.lower().split()
