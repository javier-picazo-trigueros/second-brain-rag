"""Qué quiere la pregunta: una búsqueda normal o una visión general de una asignatura o tema.

Se escribe como se habla: «de q va», «q se da», «cuantos temas tiene», sin tildes, con faltas y con
relleno («sabes», «todo»). Por eso no se busca una frase exacta sino señales sueltas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from secondbrain.retrieval.subjects import Subject, SubjectIndex, norm

Kind = Literal["search", "overview_subject", "overview_topic", "exercises", "notes"]

# Sobre el texto normalizado (sin acentos ni signos) y con las abreviaturas expandidas.
_OVERVIEW = re.compile(
    r"\b(?:"
    r"de que (?:trata|tratan|va|vamos|se trata|iba|es)|"
    r"que (?:se )?(?:da|ve|explica|explican|estudia|estudian|entra|entran|contiene|incluye|abarca|"
    r"cubre|aprende|aprendo|aprenden|temas|contenidos|unidades|apartados|bloques|lecciones)|"
    r"(?:cuantos|cuantas|cuales|numero de|lista de|listado de|enumera\w*)\W+(?:\w+\W+){0,3}?"
    r"(?:temas|unidades|apartados|bloques|lecciones|topics)|"
    r"(?:resum\w*|sintetiza\w*|temario|programa|vision general|esquema|sinopsis|indice|guion)|"
    r"en que consiste|que cosas destacarias|"
    r"(?:explica\w*|habla\w*|cuenta\w*|descri\w*|presenta\w*) (?:me )?(?:de |sobre )?"
    r"(?:la |el )?(?:asignatura|materia|tema|temario)"
    r")\b"
)
# «la asignatura de X»: nombrar la asignatura como tal ya es pedir una visión general.
_NOUN = re.compile(r"\b(?:asignatura|materia|temario)\b")
_TOPIC = re.compile(r"\b(?:tema|unidad|unit|capitulo)\s*(?:numero\s*)?(\d{1,2})\b")
_ABBREVIATIONS = (
    (re.compile(r"\bq\b"), "que"),
    (re.compile(r"\b(?:xq|pq|porq)\b"), "por que"),
    (re.compile(r"\bk\b"), "que"),
)
# «los ejercicios / el problema / el taller»: tolera faltas («ejercisios», «ejercicos»).
_EXERCISES = re.compile(r"\b(?:ejer\w{3,9}|problemas?|actividad(?:es)?|talleres|taller)\b")
# «unos apuntes del tema N» o «explícame en detalle el tema N» (con alguna falta: «aputnes»).
_NOTES = re.compile(
    r"\b(?:apunt\w*|aputn\w*|apnut\w*)\b|"
    r"\b(?:en detalle|con detalle|detalladamente|a fondo|en profundidad|con profundidad)\b"
)
_SUMMARY_WORD = re.compile(r"\bresum\w*")
# Preguntas concretas aunque nombren una asignatura: no son visión general.
_CONCRETE = re.compile(
    r"\b(?:como|por que|para que|cual es la diferencia|diferencia|define|definicion|ejemplo|"
    r"calcula\w*|implementa\w*|demuestra\w*|resuelve\w*|que es (?:un|una|el|la))\b"
)


@dataclass(frozen=True, slots=True)
class Intent:
    kind: Kind
    subject: Subject | None = None
    topic: int | None = None


def _normalize(question: str) -> str:
    text = norm(question)
    for pattern, replacement in _ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    return text


def detect_intent(question: str, index: SubjectIndex) -> Intent:
    """Visión general solo si la pregunta la pide Y nombra una asignatura conocida.

    Las preguntas concretas que mencionan una asignatura («¿cómo se calcula X en data mining?»)
    siguen siendo búsquedas normales: filtrar por asignatura ahí daría falsos positivos.
    """
    text = _normalize(question)
    subject = index.detect(question)
    if subject is None:
        return Intent("search")
    # «los ejercicios del tema N de X» (resolverlos, explicarlos, listarlos): modo ejercicios.
    topic_asked = _TOPIC.search(text)
    if topic_asked and _EXERCISES.search(text):
        return Intent("exercises", subject, int(topic_asked.group(1)))
    # Apuntes o explicación detallada del tema N (un «resumen» sigue siendo visión general).
    if topic_asked and _NOTES.search(text) and not _SUMMARY_WORD.search(text):
        return Intent("notes", subject, int(topic_asked.group(1)))
    asks_overview = _OVERVIEW.search(text) is not None
    names_the_course = _NOUN.search(text) is not None and _CONCRETE.search(text) is None
    if not (asks_overview or names_the_course):
        return Intent("search")
    topic = _TOPIC.search(text)
    if topic:
        return Intent("overview_topic", subject, int(topic.group(1)))
    return Intent("overview_subject", subject)
