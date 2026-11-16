"""El servidor MCP como proceso real hablando stdio, lanzado desde OTRO directorio de trabajo,
contra Ollama y Qdrant reales sobre el vault de EJEMPLO (nunca el real)."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

pytestmark = pytest.mark.integration

IPTABLES = "4º/Seguridad/Cortafuegos con iptables.md"


@pytest.fixture(scope="module")
def params(
    vault: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[StdioServerParameters]:
    tmp = tmp_path_factory.mktemp("mcp")
    elsewhere = tmp / "otro-directorio"
    elsewhere.mkdir()
    brain = {
        "BRAIN_VAULT_PATH": str(vault),
        "BRAIN_COLLECTION": f"test_mcp_{uuid.uuid4().hex[:8]}",
        "BRAIN_MANIFEST_PATH": str(tmp / "manifest.sqlite"),
        "BRAIN_ENV_FILE": str(tmp / "no-existe.env"),
    }
    patch = pytest.MonkeyPatch()
    for key, value in brain.items():
        patch.setenv(key, value)
    settings = Settings(_env_file=None).model_copy(update={"embed_on_cpu": True})  # type: ignore[call-arg]
    embedder = OllamaEmbedder(settings)
    store = VectorStore(settings, dim=embedder.dimension())
    store.ensure_collection()
    manifest = Manifest(settings.manifest_path)
    Indexer(settings, embedder, store, manifest).sync()
    manifest.close()
    try:
        yield StdioServerParameters(
            command=sys.executable,
            args=["-m", "secondbrain.mcp_server"],
            env={**os.environ, **brain},
            cwd=str(elsewhere),
        )
    finally:
        store.delete_collection()
        patch.undo()


def run_session(params: StdioServerParameters, calls: list[tuple[str, dict[str, Any]]]) -> Any:
    async def main() -> tuple[Any, list[CallToolResult]]:
        async with Client(params) as client:
            tools = await client.list_tools()
            results = []
            for name, args in calls:
                result = await client.call_tool(name, args)
                assert isinstance(result, CallToolResult)
                results.append(result)
            return tools, results

    return anyio.run(main)


def test_the_server_starts_from_any_directory_and_lists_its_tools(
    params: StdioServerParameters,
) -> None:
    tools, _ = run_session(params, [])
    assert {t.name for t in tools.tools} == {"search_notes", "get_note", "related_notes"}


def test_search_and_read_through_the_real_protocol(params: StdioServerParameters) -> None:
    _, (search, note) = run_session(
        params,
        [
            ("search_notes", {"query": "iptables", "k": 3}),
            ("get_note", {"path_or_title": "Cortafuegos con iptables"}),
        ],
    )
    assert search.is_error is False and search.structured_content is not None
    assert search.structured_content["notes"][0]["path"] == IPTABLES
    assert note.structured_content is not None
    assert "DROP" in note.structured_content["content"]


def test_tool_errors_reach_the_client_with_their_message(params: StdioServerParameters) -> None:
    _, (missing,) = run_session(params, [("get_note", {"path_or_title": "no existe"})])
    assert missing.is_error is True
    assert "No encuentro" in "".join(getattr(c, "text", "") for c in missing.content)
