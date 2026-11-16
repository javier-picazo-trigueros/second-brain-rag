from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from secondbrain.ingest.parser import parse_note
from secondbrain.mcp_server import McpServices, build_server
from secondbrain.retrieval.hybrid import HybridRetriever
from tests.env import Env

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
SEMAFOROS = "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md"
ENLACES = "1º/IA/Enlaces y embeds.md"

MakeServer = Callable[..., MCPServer]


@pytest.fixture
def make_server(env: Env) -> MakeServer:
    def _make(**settings: Any) -> MCPServer:
        env.indexer().sync()
        s = env.settings(**settings)
        retriever = HybridRetriever(s, env.embedder, env.store, env.manifest)
        return build_server(McpServices(s, retriever, env.manifest))

    return _make


def call(server: MCPServer, name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = anyio.run(server.call_tool, name, args)
    assert isinstance(result, CallToolResult)
    assert result.is_error is False
    assert result.structured_content is not None
    return dict(result.structured_content)


# --- catálogo ------------------------------------------------------------------------------------


def test_exposes_exactly_the_three_read_only_tools(make_server: MakeServer) -> None:
    tools = anyio.run(make_server().list_tools)
    assert {t.name for t in tools} == {"search_notes", "get_note", "related_notes"}
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is False
        assert tool.description


def test_instructions_say_it_is_read_only_and_how_to_use_the_results(
    make_server: MakeServer,
) -> None:
    instructions = make_server().instructions or ""
    assert "solo lectura" in instructions.lower()
    assert "ruta" in instructions.lower()


# --- search_notes --------------------------------------------------------------------------------


def test_search_notes_returns_compact_results(make_server: MakeServer) -> None:
    body = call(make_server(), "search_notes", {"query": "estrategias"})
    first = body["notes"][0]
    assert first["path"] == CARRERA and first["title"] == "Condiciones de carrera"
    assert first["asignatura"] == "SISTEMAS OPERATIVOS" and first["curso"] == "1º"
    assert first["heading"] and first["snippet"]
    assert {r["path"] for r in body["related"]} == {SEMAFOROS, ENLACES}
    assert body["related"][0]["via"] == ["semaforo"]


def test_snippets_are_bounded(make_server: MakeServer) -> None:
    body = call(make_server(mcp_snippet_chars=60), "search_notes", {"query": "estrategias"})
    assert all(len(n["snippet"]) <= 61 for n in body["notes"])


def test_related_can_be_left_out(make_server: MakeServer) -> None:
    body = call(make_server(), "search_notes", {"query": "estrategias", "include_related": False})
    assert body["related"] == []


@pytest.mark.parametrize("args", [{"query": ""}, {"query": "x", "k": 0}, {"query": "x", "k": 11}])
def test_search_notes_rejects_invalid_arguments(
    make_server: MakeServer, args: dict[str, Any]
) -> None:
    with pytest.raises(ToolError):
        anyio.run(make_server().call_tool, "search_notes", args)


# --- get_note ------------------------------------------------------------------------------------


def test_get_note_by_title_returns_metadata_and_content(make_server: MakeServer, env: Env) -> None:
    body = call(make_server(), "get_note", {"path_or_title": "condiciones de carrera"})
    parsed = parse_note(env.vault / CARRERA, env.vault)
    assert body["path"] == CARRERA and body["title"] == "Condiciones de carrera"
    assert body["frontmatter"]["asignatura"] == "SISTEMAS OPERATIVOS"
    assert body["frontmatter"]["conceptos"] == ["condicion de carrera", "semaforo"]
    assert "original" not in body["frontmatter"]
    assert body["content"] == parsed.body and body["total_chars"] == len(parsed.body)
    assert (body["truncated"], body["next_offset"]) == (False, None)


def test_get_note_by_path(make_server: MakeServer) -> None:
    assert call(make_server(), "get_note", {"path_or_title": SEMAFOROS})["path"] == SEMAFOROS


def test_get_note_reads_utf16_notes(make_server: MakeServer) -> None:
    body = call(make_server(), "get_note", {"path_or_title": "README"})
    assert "Guía del proyecto DIS" in body["content"]


def test_long_notes_are_paged(make_server: MakeServer) -> None:
    server = make_server()
    first = call(server, "get_note", {"path_or_title": CARRERA, "max_chars": 200})
    assert len(first["content"]) == 200 and first["truncated"] is True
    assert first["next_offset"] == 200
    second = call(server, "get_note", {"path_or_title": CARRERA, "max_chars": 200, "offset": 200})
    assert second["offset"] == 200 and second["content"] != first["content"]
    rest = call(server, "get_note", {"path_or_title": CARRERA, "offset": 200})
    assert (
        first["content"] + rest["content"]
        == call(server, "get_note", {"path_or_title": CARRERA})["content"]
    )


def test_the_page_size_is_capped_by_the_settings(make_server: MakeServer) -> None:
    body = call(
        make_server(mcp_max_chars=1000), "get_note", {"path_or_title": CARRERA, "max_chars": 50000}
    )
    assert len(body["content"]) <= 1000 and body["truncated"] is True


def test_an_unknown_note_has_a_useful_message(make_server: MakeServer) -> None:
    with pytest.raises(ToolError, match="No encuentro"):
        anyio.run(make_server().call_tool, "get_note", {"path_or_title": "no existe"})


def test_an_ambiguous_title_lists_the_candidates(make_server: MakeServer, env: Env) -> None:
    env.write("2º/IA/Sin frontmatter.md", "# Otra\n\n" + "texto distinto de la otra nota " * 20)
    with pytest.raises(ToolError) as error:
        anyio.run(make_server().call_tool, "get_note", {"path_or_title": "Sin frontmatter"})
    assert "1º/IA/Sin frontmatter.md" in str(error.value) and "2º/IA/Sin frontmatter.md" in str(
        error.value
    )


@pytest.mark.parametrize("path", ["_conceptos/semaforo.md", "../secreto.md", "x.png"])
def test_only_indexed_notes_can_be_read(make_server: MakeServer, path: str) -> None:
    with pytest.raises(ToolError):
        anyio.run(make_server().call_tool, "get_note", {"path_or_title": path})


# --- related_notes -------------------------------------------------------------------------------


def test_related_notes_lists_concepts_and_neighbours(make_server: MakeServer) -> None:
    body = call(make_server(), "related_notes", {"path_or_title": "Condiciones de carrera"})
    assert body["path"] == CARRERA
    assert body["concepts"] == ["condicion de carrera", "semaforo"]
    assert {r["path"] for r in body["related"]} == {SEMAFOROS, ENLACES}
    assert body["related"][0]["via"] == ["semaforo"]


def test_related_notes_respects_the_limit(make_server: MakeServer) -> None:
    body = call(make_server(), "related_notes", {"path_or_title": CARRERA, "limit": 1})
    assert len(body["related"]) == 1


def test_related_notes_of_an_unknown_note_fails_clearly(make_server: MakeServer) -> None:
    with pytest.raises(ToolError, match="No encuentro"):
        anyio.run(make_server().call_tool, "related_notes", {"path_or_title": "no existe"})
