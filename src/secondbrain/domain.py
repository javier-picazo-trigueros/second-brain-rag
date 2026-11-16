from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedNote:
    path: str  # relativa al vault, con "/"
    title: str
    frontmatter: dict[str, Any]
    tags: tuple[str, ...]
    links: tuple[str, ...]  # destinos de [[...]] (cuerpo + frontmatter)
    body: str
    content_hash: str
