from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import NoteHit, RelatedNote, SearchResult

# Medido con Ollama sobre chunks reales: 3,29-3,85 caracteres por token. Se usa 3,0, que
# sobreestima ~10 % y por tanto nunca se queda corto.
CHARS_PER_TOKEN = 3.0

_MIN_FRAGMENT_TOKENS = 150  # por debajo de este hueco no merece la pena meter un chunk recortado
_HINT_CHARS = 300
_ELLIPSIS = " […]"
_SOURCES_HEADER = "FUENTES (evidencia):\n\n"
_HINTS_HEADER = "NOTAS RELACIONADAS (pistas automáticas; no son evidencia):\n"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class Source:
    """Una nota presente en el contexto: lo único que el modelo puede citar."""

    label: str  # lo que va entre [[ ]]: el título, o carpeta/título si hay títulos repetidos
    path: str
    title: str
    kind: Literal["evidence", "hint"]
    pages: tuple[int, ...]
    asignatura: str | None
    curso: str | None
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class BuiltContext:
    text: str
    sources: tuple[Source, ...]
    tokens: int
    dropped_notes: int  # notas del ranking que no cupieron en el presupuesto
    mode: str = "search"  # "overview": cada nota es un resumen, no un fragmento


def _title(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def _labels(paths: Iterable[str]) -> dict[str, str]:
    """Título de cada nota; si dos notas comparten título, se usa la ruta sin extensión."""
    unique = list(dict.fromkeys(paths))
    count: dict[str, int] = {}
    for path in unique:
        count[_title(path)] = count.get(_title(path), 0) + 1
    return {p: (p.removesuffix(".md") if count[_title(p)] > 1 else _title(p)) for p in unique}


def _header(label: str, payload: dict[str, object]) -> str:
    """Título citable en su propia línea y los metadatos aparte, con etiquetas.

    Si la cabecera fuera `### [[Nota]] (asignatura) | encabezado | p. 7`, el modelo la imita
    detrás de sus citas y la página deja de ir pegada a la cita (visto con qwen2.5:7b).
    """
    fields = [
        ("Asignatura", payload.get("asignatura")),
        ("Curso", payload.get("curso")),
        ("Encabezado", payload.get("heading_path")),
        ("Página", payload.get("page")),
    ]
    meta = " · ".join(f"{name}: {value}" for name, value in fields if value not in (None, ""))
    title = f"### [[{label}]]"
    return f"{title}\n{meta}" if meta else title


def _truncate(text: str, max_tokens: int) -> str:
    """Recorta a `max_tokens`, mejor en un salto de párrafo o de frase que a mitad de palabra."""
    max_chars = max(0, int(max_tokens * CHARS_PER_TOKEN) - len(_ELLIPSIS))
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    paragraph = cut.rfind("\n\n")
    if paragraph >= max_chars * 0.5:
        cut = cut[:paragraph]
    else:
        sentence = max(cut.rfind(". "), cut.rfind("\n"))
        if sentence >= max_chars * 0.5:
            cut = cut[: sentence + 1]
    return cut.rstrip() + _ELLIPSIS


def _fit_block(header: str, text: str, room_tokens: int) -> str | None:
    """Bloque recortado para que quepa en `room_tokens`, o None si no queda sitio útil."""
    text_budget = room_tokens - estimate_tokens(header + "\n\n\n") - 1
    if text_budget < _MIN_FRAGMENT_TOKENS // 2:
        return None
    while text_budget > 0:
        block = f"{header}\n{_truncate(text, text_budget)}\n\n"
        if estimate_tokens(block) <= room_tokens:
            return block
        text_budget -= max(1, text_budget // 10)
    return None


def build_context(result: SearchResult, settings: Settings) -> BuiltContext:
    """Contexto para el modelo dentro del presupuesto: evidencia primero, pistas después."""
    labels = _labels([n.path for n in result.notes] + [r.path for r in result.related])
    overview = result.mode == "overview"  # sin pistas del grafo: todo el presupuesto es evidencia
    main_budget = settings.context_budget_tokens - (
        0 if overview else settings.related_budget_tokens
    )

    sources: list[Source] = []
    body = ""
    full = False
    dropped = 0
    for note in result.notes:
        if full:
            dropped += 1
            continue
        included, pages, was_cut, body, full = _add_note(note, labels[note.path], body, main_budget)
        if included:
            first = note.chunks[0].payload
            sources.append(
                Source(
                    label=labels[note.path],
                    path=note.path,
                    title=note.title,
                    kind="evidence",
                    pages=pages,
                    asignatura=first.get("asignatura"),
                    curso=first.get("curso"),
                    truncated=was_cut,
                )
            )
        else:
            dropped += 1

    text = _SOURCES_HEADER + body.rstrip() if body else ""
    if body and settings.related_budget_tokens > 0:
        hint_text, hints = _build_hints(result.related, labels, settings, text)
        if hints:
            text = f"{text}\n\n{hint_text}"
            sources.extend(hints_to_sources(hints, labels))
    return BuiltContext(text, tuple(sources), estimate_tokens(text), dropped, result.mode)


def _add_note(
    note: NoteHit, label: str, body: str, budget: int
) -> tuple[bool, tuple[int, ...], bool, str, bool]:
    """Añade los chunks de una nota mientras quepan. Devuelve (algo incluido, páginas, recortado,
    cuerpo nuevo, presupuesto agotado)."""
    pages: list[int] = []
    cut = False
    included = False
    for hit in note.chunks:
        block = _block(label, hit)
        room = budget - estimate_tokens(_SOURCES_HEADER + body)
        if estimate_tokens(_SOURCES_HEADER + body + block) <= budget:
            body += block
        else:
            fitted = _fit_block(_header(label, hit.payload), str(hit.payload["text"]), room)
            if fitted is None:
                return included, tuple(sorted(set(pages))), cut, body, True
            body += fitted
            cut = True
            _record(pages, hit)
            return True, tuple(sorted(set(pages))), cut, body, True
        _record(pages, hit)
        included = True
    return included, tuple(sorted(set(pages))), cut, body, False


def _record(pages: list[int], hit: Hit) -> None:
    page = hit.payload.get("page")
    if page is not None:
        pages.append(int(page))


def _block(label: str, hit: Hit) -> str:
    return f"{_header(label, hit.payload)}\n{hit.payload['text']}\n\n"


def _build_hints(
    related: list[RelatedNote], labels: dict[str, str], settings: Settings, main_text: str
) -> tuple[str, list[RelatedNote]]:
    chosen: list[RelatedNote] = []
    section = _HINTS_HEADER
    for rel in related:
        candidate = section + _hint_line(rel, labels[rel.path])
        fits_own = estimate_tokens(candidate) <= settings.related_budget_tokens
        fits_total = (
            estimate_tokens(f"{main_text}\n\n{candidate}") <= settings.context_budget_tokens
        )
        if not (fits_own and fits_total):
            break
        section = candidate
        chosen.append(rel)
    return section.rstrip(), chosen


def _hint_line(rel: RelatedNote, label: str) -> str:
    detail = rel.resumen or rel.snippet
    tail = f": {detail.replace(chr(10), ' ')[:_HINT_CHARS]}" if detail else ""
    return f"- [[{label}]]{tail}\n"


def hints_to_sources(hints: list[RelatedNote], labels: dict[str, str]) -> list[Source]:
    return [
        Source(
            label=labels[h.path],
            path=h.path,
            title=_title(h.path),
            kind="hint",
            pages=(),
            asignatura=None,
            curso=None,
        )
        for h in hints
    ]
