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
    "la fuente que citas.\n"
    "2. Cita cada afirmación con el identificador de su fuente entre corchetes, justo después de "
    "la frase: [S3]. Si varias fuentes la respaldan, [S1][S4]. Usa solo identificadores que "
    "aparezcan en las FUENTES. No escribas títulos de notas, páginas, asignaturas ni cursos: "
    "eso lo añade el sistema. Ejemplo: Un semáforo es un contador [S2].\n"
    f"3. Si las FUENTES no bastan para responder, contesta exactamente: {NOT_FOUND} "
    "Opcionalmente, en otra línea: Podrías mirar: [S2] (un identificador de las FUENTES).\n"
    "4. Las NOTAS RELACIONADAS son pistas automáticas, no evidencia: no afirmes nada "
    'basándote solo en ellas; menciónalas al final como "Ver también: [S7]".\n'
    "5. Responde en el idioma de la pregunta, de forma completa y bien estructurada: explica con "
    "tus palabras sin copiar párrafos enteros, usa párrafos cortos o listas con viñetas y, si la "
    "pregunta es amplia, subtítulos en negrita. Incluye los datos concretos que den las fuentes "
    "(definiciones, pasos, fórmulas, ejemplos); no resumas en una frase lo que desarrollan."
)

OVERVIEW_PROMPT = (
    "\n6. Esta es una pregunta de visión general: cada fuente es el resumen de una nota, con sus "
    "conceptos y apartados. Empieza con una frase que diga de qué trata el conjunto; después, "
    "una lista de los temas o bloques principales (agrupa las fuentes afines; una o dos frases "
    "por bloque, cada una con su cita); y termina con «Destacaría:» y tres o cuatro ideas clave. "
    "No inventes temas que no estén en las fuentes."
)


def build_messages(question: str, context: BuiltContext) -> list[Message]:
    asked = question.strip()
    if len(asked) > QUESTION_MAX_CHARS:
        asked = asked[:QUESTION_MAX_CHARS].rstrip() + " […]"
    sources = context.text or "FUENTES: (no se ha recuperado ninguna nota)"
    system = SYSTEM_PROMPT + (OVERVIEW_PROMPT if context.mode == "overview" else "")
    return [
        Message("system", system),
        Message("user", f"{sources}\n\nPREGUNTA: {asked}"),
    ]
