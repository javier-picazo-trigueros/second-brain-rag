from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import yaml

from secondbrain.domain import ParsedNote

_FM = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_FENCED = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_WIKILINK = re.compile(r"(?<!!)\[\[([^\]\|#\^\n]+)(?:[#^][^\]\|\n]*)?(?:\|[^\]\n]*)?\]\]")
_TAG = re.compile(r"(?<![\w/&])#([^\W\d][\w/\-]*)")

# Campos del frontmatter que apuntan a ficheros fuente y no a otras notas.
_SKIP_LINK_FIELDS = frozenset({"original"})
# Destinos de [[...]] que son archivos adjuntos y no notas.
_NON_NOTE_EXTENSIONS = frozenset(
    {
        "pdf", "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico",
        "mp3", "wav", "ogg", "m4a", "mp4", "webm", "mov", "mkv",
        "docx", "doc", "pptx", "ppt", "xlsx", "xls", "zip", "csv", "excalidraw",
    }
)  # fmt: skip


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):  # hay README en UTF-16 en el vault
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text[m.end() :]
    return (data if isinstance(data, dict) else {}), text[m.end() :]


def _strip_code(text: str) -> str:
    return _INLINE_CODE.sub("", _FENCED.sub("", text))


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _iter_strings(v)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i for i in items if i))


def _is_note_target(target: str) -> bool:
    _, dot, ext = target.rpartition(".")
    return not (dot and ext.lower() in _NON_NOTE_EXTENSIONS)


def _targets(text: str) -> Iterator[str]:
    for m in _WIKILINK.finditer(text):
        target = m.group(1).strip().rsplit("/", 1)[-1]
        if _is_note_target(target):
            yield target


def parse_note(abs_path: Path, vault: Path) -> ParsedNote:
    raw = abs_path.read_bytes()
    fm, body = _split_frontmatter(_decode(raw))
    scan = _strip_code(body)

    link_fields = {k: v for k, v in fm.items() if k not in _SKIP_LINK_FIELDS}
    fm_links = (t for s in _iter_strings(link_fields) for t in _targets(s))
    links = _dedupe((*_targets(scan), *fm_links))

    raw_tags = fm.get("tags", [])
    fm_tags = [raw_tags] if isinstance(raw_tags, str) else list(_iter_strings(raw_tags))
    inline = (m.group(1) for m in _TAG.finditer(scan))
    tags = _dedupe(t.lstrip("#").lower() for t in (*fm_tags, *inline))

    return ParsedNote(
        path=abs_path.relative_to(vault).as_posix(),
        title=abs_path.stem,
        frontmatter=fm,
        tags=tags,
        links=links,
        body=body,
        content_hash=hashlib.sha256(raw).hexdigest(),
    )
