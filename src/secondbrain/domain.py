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


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    note_path: str
    note_title: str
    heading_path: tuple[str, ...]
    text: str
    position: int
    tags: tuple[str, ...]
    links: tuple[str, ...]
    asignatura: str | None
    curso: str | None
    resumen: str | None
    page: int | None  # página del PDF original, si la nota la marca con "## Página N"

    @property
    def embed_text(self) -> str:
        """Texto que se embebe: contexto (título > encabezados) + contenido."""
        ctx = " > ".join((self.note_title, *self.heading_path))
        return f"{ctx}\n\n{self.text}"


@dataclass(frozen=True, slots=True)
class Hit:
    score: float
    payload: dict[str, Any]
