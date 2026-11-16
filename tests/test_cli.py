from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException
from typer.testing import CliRunner

from secondbrain import cli
from secondbrain.cli import Services, app
from tests.env import Env

runner = CliRunner()


@pytest.fixture
def wired(env: Env, monkeypatch: pytest.MonkeyPatch) -> Env:
    """Sustituye la construcción de servicios por fakes sobre el vault de ejemplo."""
    monkeypatch.setattr(
        cli,
        "_build",
        lambda: Services(env.settings(), env.embedder, env.store, env.manifest),
    )
    return env


# --- brain index -----------------------------------------------------------------------------


def test_index_prints_summary(wired: Env) -> None:
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0, result.output
    assert "indexadas=9 sin_cambios=0 vacias=1 borradas=0 fallos=0" in result.output


def test_second_index_reports_zero_indexed(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["index"])
    assert "indexadas=0 sin_cambios=10 vacias=0 borradas=0 fallos=0" in result.output


def test_index_with_failures_lists_them_and_exits_with_error(wired: Env) -> None:
    wired.embedder.fail_on = "iptables"
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 1
    assert "fallos=1" in result.output
    assert "FALLO 4º/Seguridad/Cortafuegos con iptables.md" in result.output


# --- brain search ----------------------------------------------------------------------------


def test_search_shows_path_heading_and_snippet(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "iptables"])
    assert result.exit_code == 0, result.output
    assert "4º/Seguridad/Cortafuegos con iptables.md" in result.output
    assert "[Cortafuegos con iptables" in result.output


def test_search_respects_k(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "de", "-k", "2", "--no-graph"])
    shown = [ln for ln in result.output.splitlines() if ".md" in ln]
    assert len(shown) == 2


def test_search_shows_page_when_known(wired: Env) -> None:
    wired.write("1º/IA/Paginada.md", "## Página 4\n\n# Tema\n\n" + "contenido paginado " * 30)
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "paginado"])
    assert "p. 4" in result.output


def test_search_without_results_says_so(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "xyzzy"])
    assert result.exit_code == 0
    assert "Sin resultados" in result.output


# --- brain stats -----------------------------------------------------------------------------


def test_stats_reports_notes_chunks_and_points(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["stats"])
    notes, chunks = wired.manifest.totals()
    assert result.exit_code == 0, result.output
    assert f"notas={notes} chunks_manifest={chunks} puntos_qdrant={wired.store.count()}" in (
        result.output
    )


# --- errores de entorno con mensajes útiles ---------------------------------------------------


@pytest.fixture
def real_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Usa _build de verdad (sin fakes) con una configuración mínima válida."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRAIN_VAULT_PATH", str(tmp_path))


def test_missing_configuration_explains_what_to_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BRAIN_VAULT_PATH", raising=False)
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 2
    assert "BRAIN_VAULT_PATH" in result.output


@pytest.mark.usefixtures("real_build")
def test_ollama_down_tells_how_to_start_it(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def dimension(self) -> int:
            raise httpx.ConnectError("sin conexión")

    monkeypatch.setattr(cli, "OllamaEmbedder", Down)
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 2
    assert "Ollama no responde" in result.output
    assert "ollama serve" in result.output


@pytest.mark.usefixtures("real_build")
def test_missing_embedding_model_tells_which_pull_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoModel:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def dimension(self) -> int:
            request = httpx.Request("POST", "http://localhost:11434/api/embed")
            raise httpx.HTTPStatusError(
                "404", request=request, response=httpx.Response(404, request=request)
            )

    monkeypatch.setattr(cli, "OllamaEmbedder", NoModel)
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 2
    assert "ollama pull bge-m3" in result.output


@pytest.mark.usefixtures("real_build")
def test_qdrant_down_tells_how_to_start_it(monkeypatch: pytest.MonkeyPatch) -> None:
    class Ok:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def dimension(self) -> int:
            return 3

    class QdrantDown:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def ensure_collection(self) -> None:
            raise ResponseHandlingException(httpx.ConnectError("sin conexión"))

    monkeypatch.setattr(cli, "OllamaEmbedder", Ok)
    monkeypatch.setattr(cli, "VectorStore", QdrantDown)
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 2
    assert "Qdrant no responde" in result.output
    assert "tasks.ps1 up" in result.output


# --- búsqueda híbrida: copias y relacionadas ----------------------------------------


def test_search_collapses_exact_copies_and_lists_the_other_locations(wired: Env) -> None:
    original = (wired.vault / "1º/IA/Sin frontmatter.md").read_text(encoding="utf-8")
    wired.write("1º/IA/Sin frontmatter (1).md", original)
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "regularización", "--no-graph"])
    lines = result.output.splitlines()
    assert sum("1º/IA/Sin frontmatter.md" in ln and "también en" not in ln for ln in lines) == 1
    assert any("también en:" in ln and "Sin frontmatter (1).md" in ln for ln in lines)


def test_search_lists_related_notes_in_a_separate_section(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "estrategias"])
    head, _, related = result.output.partition("Relacionadas por el grafo")
    assert "Condiciones de carrera.md" in head
    assert "Semáforos y monitores.md" in related
    assert "semaforo" in related
    assert "Semáforos y monitores.md" not in head


def test_no_graph_flag_hides_the_related_section(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["search", "estrategias", "--no-graph"])
    assert "Relacionadas" not in result.output


# --- brain graph -----------------------------------------------------------------------------


def test_graph_by_title_shows_concepts_and_neighbours(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["graph", "Condiciones de carrera"])
    assert result.exit_code == 0, result.output
    assert "condicion de carrera, semaforo" in result.output
    assert "Semáforos y monitores.md" in result.output
    assert "Enlaces y embeds.md" in result.output


def test_graph_accepts_the_full_path(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["graph", "4º/Seguridad/Cortafuegos con iptables.md"])
    assert result.exit_code == 0, result.output
    assert "Enlaces y embeds.md" in result.output


def test_graph_of_an_unknown_note_fails_with_a_message(wired: Env) -> None:
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["graph", "no existe"])
    assert result.exit_code == 1
    assert "No encuentro" in result.output


def test_graph_with_an_ambiguous_title_lists_the_candidates(wired: Env) -> None:
    runner.invoke(app, ["index"])
    wired.write("2º/IA/Sin frontmatter.md", "# Otra\n\n" + "texto distinto de la otra nota " * 20)
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["graph", "Sin frontmatter"])
    assert result.exit_code == 1
    assert "1º/IA/Sin frontmatter.md" in result.output
    assert "2º/IA/Sin frontmatter.md" in result.output


# --- brain watch y stats ----------------------------------------------------------------------


def test_watch_syncs_first_and_then_watches(wired: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    class FakeWatcher:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def run(self, stop: Any) -> None:
            started.append("run")

    monkeypatch.setattr(cli, "WatcherService", FakeWatcher)
    result = runner.invoke(app, ["watch"])
    assert result.exit_code == 0, result.output
    assert "indexadas=9" in result.output
    assert "Vigilando" in result.output
    assert started == ["run"]


def test_watch_stops_cleanly_on_ctrl_c(wired: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    class Interrupted:
        def __init__(self, *_: Any, **__: Any) -> None: ...

        def run(self, stop: Any) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "WatcherService", Interrupted)
    result = runner.invoke(app, ["watch"])
    assert result.exit_code == 0, result.output
    assert "Detenido" in result.output


def test_stats_reports_copy_groups_and_concepts(wired: Env) -> None:
    original = (wired.vault / "1º/IA/Sin frontmatter.md").read_text(encoding="utf-8")
    wired.write("1º/IA/Sin frontmatter (1).md", original)
    runner.invoke(app, ["index"])
    result = runner.invoke(app, ["stats"])
    assert "grupos_de_copias=1" in result.output
    assert "conceptos=3" in result.output
