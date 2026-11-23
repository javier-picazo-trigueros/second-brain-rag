"""Temas (unidades) de una asignatura, sacados de los nombres de archivo del índice.

El número de temas de una asignatura es un dato del índice («Unit 1»…«Unit 7»), no algo que deba
adivinar el modelo: se calcula aquí y se le pasa como dato.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

_MARKER = re.compile(
    r"(?<![a-z0-9])(?:tema|unit|unidad|topic|leccion|lesson)[\s_-]*0?(\d{1,2})(?:\.(\d{1,2}))?(?!\d)"
)
# Marca corta: «T2», «CAR_T2», «T02». Una sola cifra y sin letras ni cifras pegadas detrás, para que
# «T20», «T22» o «T2a» no cuenten como el tema 2.
_SHORT_MARKER = re.compile(r"(?<![a-z0-9])t0?([1-9])(?:\.(\d{1,2}))?(?![a-z0-9])")
_SHORT_LEADING = re.compile(
    r"^.*?(?<![a-z0-9])t0?[1-9](?:\.\d{1,2})?(?![a-z0-9])[\s_.:\-–]*", re.IGNORECASE
)
_LEADING = re.compile(
    r"^.*?(?:tema|unit|unidad|topic|lecci[oó]n|lesson)[\s_-]*0?\d{1,2}(?:\.\d{1,2})?[\s_.:\-\u2013]*",
    re.IGNORECASE,
)
_COPY = re.compile(r"\s*\(\d+\)\s*$")
_VERSION = re.compile(r"(?:^|[\s_-]+)v\d+(?:\.\d+)*\s*$", re.IGNORECASE)
_EXERCISE = re.compile(
    r"\b(?:exercis\w*|ejercicio\w*|solution|solucion\w*|taller|practic\w*|lab\w*|examen|test)\b"
)
_SOLUTION = re.compile(r"\b(?:solutions?|soluciones|solucion(?:es|ario)?)\b")
_GUIDE = re.compile(
    r"\b(?:guia docente|guia de la asignatura|course guide|syllabus|programa de la asignatura|"
    r"plan docente|guia)\b"
)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def is_guide(title: str) -> bool:
    """¿Es la guía docente o el programa de la asignatura (no su temario)?"""
    return _GUIDE.search(re.sub(r"[_\-.]+", " ", _plain(title))) is not None


def is_solution(title: str) -> bool:
    """¿Es la solución de unos ejercicios («… - solution», «Soluciones»)?"""
    return _SOLUTION.search(re.sub(r"[_\-.]+", " ", _plain(title))) is not None


def is_exercise(title: str) -> bool:
    return _EXERCISE.search(re.sub(r"[_\-.]+", " ", _plain(title))) is not None


def topic_key(path: str) -> tuple[int, str] | None:
    """(número, «3.1») del tema que indica el nombre de la nota o, si no, su carpeta."""
    p = PurePosixPath(path)
    for name in (p.stem, p.parent.name):
        plain = _plain(name)
        match = _MARKER.search(plain) or _SHORT_MARKER.search(plain)
        if match:
            sub = (
                f"{match.group(1)}.{match.group(2)}" if match.group(2) else str(int(match.group(1)))
            )
            return int(match.group(1)), sub
    return None


def clean_title(stem: str) -> str:
    """El nombre del tema sin «Unit 2 -», sin «(1)» de copia y sin versión."""
    text = _COPY.sub("", stem)
    if _LEADING.search(text):
        text = _LEADING.sub("", text, count=1)
    elif _SHORT_LEADING.search(text):
        text = _SHORT_LEADING.sub("", text, count=1)
    return _VERSION.sub("", text).strip(" -_.")


@dataclass(frozen=True, slots=True)
class Topic:
    number: int
    titles: tuple[str, ...]  # de las notas de teoría; vacío si solo hay ejercicios
    notes: tuple[str, ...]


def index_topics(paths: Iterable[str]) -> list[Topic]:
    grouped: dict[int, list[str]] = {}
    for path in sorted(set(paths)):
        key = topic_key(path)
        if key is not None:
            grouped.setdefault(key[0], []).append(path)
    topics: list[Topic] = []
    for number in sorted(grouped):
        notes = grouped[number]
        titles: dict[str, None] = {}
        for path in notes:
            stem = PurePosixPath(path).stem
            if is_exercise(stem) or is_guide(stem):
                continue
            title = clean_title(stem)
            if title:
                titles.setdefault(title)
        topics.append(Topic(number, tuple(titles), tuple(notes)))
    return topics


def topics_fact(topics: list[Topic]) -> str:
    """Dato exacto para el modelo: cuántos temas tiene la asignatura y cuáles son."""
    if not topics:
        return ""
    n = len(topics)
    numbers = [t.number for t in topics]
    gaps = numbers != list(range(numbers[0], numbers[0] + n))
    listing = "; ".join(
        f"{t.number}. {' / '.join(t.titles)}" if t.titles else f"{t.number}." for t in topics
    )
    word = "tema" if n == 1 else "temas"
    numbering = f" (números: {', '.join(str(x) for x in numbers)})" if gaps else ""
    return (
        f"DATO DEL ÍNDICE (cuenta exacta, no la cambies): la asignatura tiene {n} {word} "
        f"numerados{numbering}. {listing}"
    )
