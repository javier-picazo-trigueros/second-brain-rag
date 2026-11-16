from __future__ import annotations

import re
import uuid

from secondbrain.domain import Chunk, ParsedNote
from secondbrain.ingest.text import PLACEHOLDER

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_PAGE_HEADING = re.compile(r"^p[aá]gina\s+(\d+)$", re.I)
_FENCE_LINE = re.compile(r"^[ \t]*(```|~~~)")
_MIN_KEEP = 40

# Súbela cuando cambie el algoritmo: fuerza a reindexar todas las notas.
CHUNKER_VERSION = 1

_Section = tuple[tuple[str, ...], int | None, str]


def _sections(body: str) -> list[_Section]:
    """Divide por encabezados (ignorando los que están dentro de bloques de código).

    Los encabezados "Página N" no entran en la jerarquía: solo cambian la página actual.
    """
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    out: list[_Section] = []
    page: int | None = None
    in_fence, marker = False, ""

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            out.append((tuple(t for _, t in stack), page, text))
        buf.clear()

    for line in body.splitlines():
        fence = _FENCE_LINE.match(line)
        if fence:
            if not in_fence:
                in_fence, marker = True, fence.group(1)
            elif fence.group(1) == marker:
                in_fence = False
        elif not in_fence:
            h = _HEADING.match(line)
            if h:
                flush()
                page_match = _PAGE_HEADING.match(h.group(2).strip())
                if page_match:
                    page = int(page_match.group(1))
                    continue
                level = len(h.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, h.group(2).strip()))
                continue
        buf.append(line)
    flush()
    return out


def _blocks(text: str) -> list[str]:
    """Párrafos separados por línea en blanco; un bloque de código es atómico."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence, marker = False, ""
    for line in text.splitlines():
        fence = _FENCE_LINE.match(line)
        if fence:
            if not in_fence:
                in_fence, marker = True, fence.group(1)
            elif fence.group(1) == marker:
                in_fence = False
            cur.append(line)
        elif not in_fence and not line.strip():
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _hard_split(block: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for line in block.splitlines():
        while len(line) > max_chars:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:max_chars])
            line = line[max_chars:]
        if cur and len(cur) + len(line) + 1 > max_chars:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def _pack(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    cur = ""
    for block in _blocks(text):
        for part in [block] if len(block) <= max_chars else _hard_split(block, max_chars):
            if cur and len(cur) + 2 + len(part) > max_chars:
                pieces.append(cur)
                cur = part
            else:
                cur = f"{cur}\n\n{part}" if cur else part
    if cur:
        pieces.append(cur)
    return pieces


def chunk_note(note: ParsedNote, max_chars: int = 1800, min_chars: int = 300) -> list[Chunk]:
    body = PLACEHOLDER.sub("", note.body)
    pieces: list[_Section] = []
    for heading_path, page, text in _sections(body):
        for piece in _pack(text, max_chars):
            if pieces and len(piece) < min_chars:
                prev_path, prev_page, prev_text = pieces[-1]
                label = (
                    f"**{heading_path[-1]}**\n"
                    if heading_path and heading_path != prev_path
                    else ""
                )
                if len(prev_text) + len(label) + len(piece) + 2 <= max_chars:
                    pieces[-1] = (prev_path, prev_page, f"{prev_text}\n\n{label}{piece}")
                    continue
            pieces.append((heading_path, page, piece))

    fm = note.frontmatter
    meta = {
        k: (str(fm[k]) if fm.get(k) is not None else None)
        for k in ("asignatura", "curso", "resumen")
    }
    kept = [p for p in pieces if len(p[2]) >= _MIN_KEEP]
    return [
        Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note.path}#{i}")),
            note_path=note.path,
            note_title=note.title,
            heading_path=hp,
            text=text,
            position=i,
            tags=note.tags,
            links=note.links,
            asignatura=meta["asignatura"],
            curso=meta["curso"],
            resumen=meta["resumen"],
            page=page,
        )
        for i, (hp, page, text) in enumerate(kept)
    ]
