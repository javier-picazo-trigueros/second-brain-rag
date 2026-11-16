"""Servidor MCP (stdio) para consultar el vault desde Claude Code u otros clientes MCP.

Solo lectura. Ojo: lo que devuelven estas herramientas pasa a la conversación del cliente, que
puede enviarlo a un servicio externo. Por eso las salidas están acotadas (`mcp_max_chars`,
`mcp_snippet_chars`) y se pueden dejar notas fuera del índice con `BRAIN_EXCLUDE_GLOBS`.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from secondbrain.api.app import Retriever
from secondbrain.config import Settings
from secondbrain.ingest.parser import parse_note
from secondbrain.notes import resolve_note
from secondbrain.retrieval.graph import ConceptGraph
from secondbrain.store.manifest import Manifest

INSTRUCTIONS = (
    "Acceso de solo lectura a un vault de Obsidian con apuntes universitarios. "
    "Usa search_notes para buscar, get_note para leer una nota y related_notes para ver las notas "
    "conectadas por conceptos. Cita siempre la ruta de la nota de la que sacas cada dato. "
    "Los resúmenes y conceptos de las notas los generó un modelo pequeño: son pistas, no hechos; "
    "verifica en el cuerpo de la nota. Si no encuentras algo en el vault, dilo."
)
_HINT_CHARS = 200


@dataclass(slots=True)
class McpServices:
    settings: Settings
    retriever: Retriever
    manifest: Manifest


class FoundNote(BaseModel):
    path: str
    title: str
    score: float
    asignatura: str | None = None
    curso: str | None = None
    heading: str | None = None
    page: int | None = None
    snippet: str
    also_in: list[str] = Field(default_factory=list, description="Copias exactas en otras rutas")


class RelatedItem(BaseModel):
    path: str
    title: str
    via: list[str] = Field(description="Conceptos que conectan ambas notas")
    hint: str | None = Field(default=None, description="Resumen automático: pista")


class SearchNotesResult(BaseModel):
    notes: list[FoundNote]
    related: list[RelatedItem]


class NoteContent(BaseModel):
    path: str
    title: str
    frontmatter: dict[str, Any]
    content: str
    offset: int
    total_chars: int
    truncated: bool
    next_offset: int | None = None


class RelatedNotesResult(BaseModel):
    path: str
    concepts: list[str]
    related: list[RelatedItem]


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def build_server(services: McpServices) -> MCPServer:
    settings = services.settings
    manifest = services.manifest
    server = MCPServer("second-brain", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )

    def resolve(wanted: str) -> str:
        matches = resolve_note(manifest.note_concepts(), wanted)
        if not matches:
            raise ToolError(
                f"No encuentro ninguna nota «{wanted}» en el índice. Prueba con search_notes."
            )
        if len(matches) > 1:
            listed = "\n".join(f"  {p}" for p in matches)
            raise ToolError(f"«{wanted}» es ambiguo. Indica la ruta completa:\n{listed}")
        return matches[0]

    @server.tool(annotations=read_only)
    def search_notes(
        query: Annotated[str, Field(min_length=1, max_length=2000, description="Qué buscar")],
        k: Annotated[int, Field(ge=1, le=10, description="Número de notas")] = 5,
        include_related: Annotated[bool, Field(description="Añadir notas relacionadas")] = True,
    ) -> SearchNotesResult:
        """Busca en los apuntes (semántica y por palabras exactas). Una entrada por nota."""
        result = services.retriever.search(query, k=k, with_graph=include_related)
        notes = []
        for n in result.notes:
            first = n.chunks[0].payload
            notes.append(
                FoundNote(
                    path=n.path,
                    title=n.title,
                    score=round(n.score, 3),
                    asignatura=first.get("asignatura"),
                    curso=first.get("curso"),
                    heading=first.get("heading_path") or None,
                    page=first.get("page"),
                    snippet=_clip(str(first.get("text", "")), settings.mcp_snippet_chars),
                    also_in=list(n.also_in),
                )
            )
        related = [
            RelatedItem(
                path=r.path,
                title=PurePosixPath(r.path).stem,
                via=list(r.via),
                hint=_clip(r.resumen or r.snippet or "", _HINT_CHARS) or None,
            )
            for r in result.related
        ]
        return SearchNotesResult(notes=notes, related=related)

    @server.tool(annotations=read_only)
    def get_note(
        path_or_title: Annotated[str, Field(description="Ruta relativa al vault o título")],
        max_chars: Annotated[int, Field(ge=100, description="Máximo de caracteres")] = 12_000,
        offset: Annotated[int, Field(ge=0, description="Desde qué carácter leer")] = 0,
    ) -> NoteContent:
        """Lee una nota (cuerpo y metadatos). Las notas largas se leen por tramos con offset."""
        path = resolve(path_or_title)
        try:
            note = parse_note(settings.vault_path / path, settings.vault_path)
        except FileNotFoundError as exc:
            raise ToolError(f"La nota {path} ya no existe en el vault.") from exc
        fm = note.frontmatter
        size = min(max_chars, settings.mcp_max_chars)
        end = offset + size
        return NoteContent(
            path=note.path,
            title=note.title,
            frontmatter={
                "asignatura": fm.get("asignatura"),
                "curso": fm.get("curso"),
                "resumen": fm.get("resumen"),
                "tags": list(note.tags),
                "conceptos": list(note.concepts),
            },
            content=note.body[offset:end],
            offset=offset,
            total_chars=len(note.body),
            truncated=end < len(note.body),
            next_offset=end if end < len(note.body) else None,
        )

    @server.tool(annotations=read_only)
    def related_notes(
        path_or_title: Annotated[str, Field(description="Ruta relativa al vault o título")],
        limit: Annotated[int, Field(ge=1, le=30, description="Notas a devolver")] = 8,
    ) -> RelatedNotesResult:
        """Notas conectadas con una nota por conceptos compartidos (grafo del vault)."""
        path = resolve(path_or_title)
        graph = ConceptGraph.from_manifest(manifest)
        found = graph.expand(
            [(path, 1.0)],
            fanout_cap=settings.graph_fanout_cap,
            budget=limit,
            min_idf=settings.graph_min_idf,
        )
        return RelatedNotesResult(
            path=path,
            concepts=list(graph.concepts_of(path)),
            related=[
                RelatedItem(path=r.path, title=PurePosixPath(r.path).stem, via=list(r.via))
                for r in found
            ],
        )

    return server


def main() -> None:
    # stdout es el canal del protocolo: todo el registro va a stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    from secondbrain.api.main import build_services  # import tardío: arranque rápido de --help

    app = build_services()
    build_server(McpServices(app.settings, app.retriever, app.manifest)).run("stdio")


if __name__ == "__main__":
    main()
