"""Qué quiere la pregunta: una búsqueda normal o una visión general de una asignatura o tema."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from secondbrain.retrieval.subjects import Subject, SubjectIndex, norm

Kind = Literal["search", "overview_subject", "overview_topic"]

# Sobre el texto normalizado (sin acentos ni signos).
_OVERVIEW = re.compile(
    r"\b(?:de que (?:trata|va)|que (?:se )?(?:da|ve|explica|estudia|entra|contiene)|"
    r"que (?:temas|contenidos)|resum\w*|temario|vision general|en que consiste|"
    r"que cosas destacarias)\b"
)
_TOPIC = re.compile(r"\b(?:tema|unidad|unit|capitulo)\s*(?:numero\s*)?(\d{1,2})\b")


@dataclass(frozen=True, slots=True)
class Intent:
    kind: Kind
    subject: Subject | None = None
    topic: int | None = None


def detect_intent(question: str, index: SubjectIndex) -> Intent:
    """Visión general solo si la pregunta la pide Y nombra una asignatura conocida.

    Las preguntas concretas que mencionan una asignatura («¿cómo se calcula X en data mining?»)
    siguen siendo búsquedas normales: filtrar por asignatura ahí daría falsos positivos.
    """
    text = norm(question)
    subject = index.detect(question)
    if subject is None or not _OVERVIEW.search(text):
        return Intent("search")
    topic = _TOPIC.search(text)
    if topic:
        return Intent("overview_topic", subject, int(topic.group(1)))
    return Intent("overview_subject", subject)
