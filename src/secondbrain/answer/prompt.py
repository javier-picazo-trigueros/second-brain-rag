from __future__ import annotations

from secondbrain.answer.context import BuiltContext
from secondbrain.answer.llm import Message

NOT_FOUND = "No lo encuentro en el vault."
QUESTION_MAX_CHARS = 2000

SYSTEM_PROMPT = (
    "Eres el asistente del vault de apuntes del usuario. "
    "Responde SOLO con la información de las FUENTES.\n"
    "Reglas:\n"
    "1. No uses conocimiento propio ni inventes datos. No extrapoles: afirma solo lo que dice "
    "el texto de la fuente que citas.\n"
    "2. Cada afirmación debe terminar con su cita [[Título]], copiando el título tal cual "
    "aparece en la fuente, y (p. N) pegado a la cita si la fuente indica página. "
    "No añadas asignatura ni curso. Ejemplo: Un semáforo es un contador [[Semáforos]] (p. 7).\n"
    f"3. Si las FUENTES no bastan para responder, contesta exactamente: {NOT_FOUND} "
    "Opcionalmente, en otra línea: Podrías mirar: [[Título]] (una nota de las FUENTES).\n"
    "4. Las NOTAS RELACIONADAS son pistas automáticas, no evidencia: no afirmes nada "
    'basándote solo en ellas; menciónalas como "Ver también".\n'
    "5. Responde en el idioma de la pregunta, de forma concisa y sin copiar párrafos enteros."
)


def build_messages(question: str, context: BuiltContext) -> list[Message]:
    asked = question.strip()
    if len(asked) > QUESTION_MAX_CHARS:
        asked = asked[:QUESTION_MAX_CHARS].rstrip() + " […]"
    sources = context.text or "FUENTES: (no se ha recuperado ninguna nota)"
    return [
        Message("system", SYSTEM_PROMPT),
        Message("user", f"{sources}\n\nPREGUNTA: {asked}"),
    ]
