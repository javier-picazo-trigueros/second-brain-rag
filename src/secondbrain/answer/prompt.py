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
    f"3. Si ninguna FUENTE trata el tema de la pregunta, contesta exactamente: {NOT_FOUND} "
    "Opcionalmente, en otra línea: Podrías mirar: [S2] (un identificador de las FUENTES).\n"
    "4. Las NOTAS RELACIONADAS son pistas automáticas, no evidencia: no afirmes nada "
    'basándote solo en ellas; menciónalas al final como "Ver también: [S7]".\n'
    "5. Responde en el idioma de la pregunta, de forma completa y bien estructurada: explica con "
    "tus palabras sin copiar párrafos enteros, usa párrafos cortos o listas con viñetas y, si la "
    "pregunta es amplia, subtítulos en negrita. Incluye los datos concretos que den las fuentes "
    "(definiciones, pasos, fórmulas, ejemplos) y no pases de unas 300 palabras salvo que la "
    "pregunta pida más. Si te piden relacionar o comparar temas, expón lo que dice cada fuente y "
    "señala las conexiones que permitan; si ninguna fuente las establece, dilo en una frase en "
    "vez de rechazar la pregunta."
)

# Al final del mensaje, donde más pesa para un modelo de 7B: en respuestas largas dejaba de citar.
REMINDER = "Recuerda: termina cada afirmación con su cita [S#] y no escribas títulos ni páginas."

OVERVIEW_PROMPT = (
    "\n6. Esta es una pregunta de visión general de una asignatura: cada fuente es el resumen de "
    "una nota, con sus conceptos y apartados. El DATO DEL ÍNDICE da el número exacto de temas y su "
    "lista: úsalo tal cual y presenta esos temas, ni más ni menos. Estructura: 1) una primera "
    "frase que diga de qué trata; 2) cuántos temas tiene; 3) por cada tema, dos o tres frases con "
    "su cita (no una lista de títulos); 4) cierra con «Destacaría:» y tres o cuatro ideas clave. "
    "Si la pregunta pide una extensión o un formato (p. ej. «un par de párrafos»), respétalo en "
    "vez de esta estructura, sin dejar de decir cuántos temas tiene. No inventes temas, "
    "requisitos ni prerrequisitos que no estén en las fuentes."
)

TOPIC_PROMPT = (
    "\n6. Esta pregunta es sobre UN tema concreto: cada fuente es el resumen de una nota de ese "
    "tema, con sus conceptos y apartados. Estructura: 1) una primera frase que diga de qué va el "
    "tema; 2) sus apartados principales, con dos o tres frases cada uno y su cita; 3) cierra con "
    "«Destacaría:» y dos o tres ideas clave. No digas cuántos temas tiene la asignatura ni "
    "cuántos apartados «en total» tiene el tema. No inventes nada que no esté en las fuentes."
)


def build_messages(question: str, context: BuiltContext) -> list[Message]:
    asked = question.strip()
    if len(asked) > QUESTION_MAX_CHARS:
        asked = asked[:QUESTION_MAX_CHARS].rstrip() + " […]"
    sources = context.text or "FUENTES: (no se ha recuperado ninguna nota)"
    extra = {"overview": OVERVIEW_PROMPT, "overview_topic": TOPIC_PROMPT}.get(context.mode, "")
    system = SYSTEM_PROMPT + extra
    return [
        Message("system", system),
        Message("user", f"{sources}\n\nPREGUNTA: {asked}\n\n{REMINDER}"),
    ]
