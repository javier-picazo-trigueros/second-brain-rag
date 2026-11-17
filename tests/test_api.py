from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.exceptions import ResponseHandlingException

from secondbrain.answer.pipeline import AnswerPipeline
from secondbrain.api.app import AppServices, create_app
from secondbrain.api.health import HealthChecker
from secondbrain.api.reindex import ReindexManager
from secondbrain.ingest.indexer import SyncReport
from secondbrain.retrieval.catalog import Catalog
from secondbrain.retrieval.hybrid import HybridRetriever, SearchResult
from tests.env import Env
from tests.fakes import ScriptedLLM

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
SEMAFOROS = "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md"
ENLACES = "1º/IA/Enlaces y embeds.md"
README = "2º/DIS/README.md"


def ollama_ok(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/version":
        return httpx.Response(200, json={"version": "0.40.6"})
    if path == "/api/tags":
        return httpx.Response(
            200, json={"models": [{"name": "bge-m3:latest"}, {"name": "qwen2.5:7b"}]}
        )
    return httpx.Response(200, json={"models": []})


@dataclass
class Api:
    client: TestClient
    env: Env
    llm: ScriptedLLM


MakeApi = Callable[..., Api]


@pytest.fixture
def make_api(env: Env) -> Iterator[MakeApi]:
    env.indexer().sync()

    def _make(
        deltas: Sequence[str] = ("Hay tres estrategias ", "[S1]."),
        *,
        retriever: Any = None,
        reindex_run: Callable[..., SyncReport] | None = None,
        warmup: Callable[[], None] | None = None,
        static_dir: Path | None = None,
        ollama: Callable[[httpx.Request], httpx.Response] = ollama_ok,
        **settings: Any,
    ) -> Api:
        s = env.settings(**settings)
        real = HybridRetriever(s, env.embedder, env.store, env.manifest)
        used = retriever or real
        llm = ScriptedLLM(deltas)
        client = httpx.Client(base_url=s.ollama_url, transport=httpx.MockTransport(ollama))
        health = HealthChecker(s, client, env.store.count)
        indexer = env.indexer(**settings)
        reindex = ReindexManager(
            reindex_run or (lambda progress: indexer.sync(on_progress=progress))
        )
        services = AppServices(
            settings=s,
            catalog=Catalog(s, env.manifest, env.store, aliases={}),
            retriever=used,
            pipeline=AnswerPipeline(s, used, llm),
            manifest=env.manifest,
            health=health.check,
            reindex=reindex,
            points=env.store.count,
            warmup=warmup,
        )
        return Api(
            TestClient(create_app(services, static_dir=static_dir), base_url="http://localhost"),
            env,
            llm,
        )

    yield _make


def sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(ln[7:] for ln in lines if ln.startswith("event: "))
        data = next(ln[6:] for ln in lines if ln.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


# --- /health y /stats ------------------------------------------------------------------------


def test_health_reports_every_component(make_api: MakeApi) -> None:
    body = make_api().client.get("/health").json()
    assert body["status"] == "ok"
    assert body["ollama"]["models"] == {"bge-m3": True, "qwen2.5:7b": True}
    assert body["qdrant"]["ok"] is True and body["qdrant"]["points"] > 0
    assert body["vault"]["ok"] is True and body["hints"] == []


def test_health_degrades_with_a_hint_when_a_model_is_missing(make_api: MakeApi) -> None:
    def only_embedder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "bge-m3:latest"}]})
        return ollama_ok(request)

    body = make_api(ollama=only_embedder).client.get("/health").json()
    assert body["status"] == "degraded"
    assert any("ollama pull qwen2.5:7b" in h for h in body["hints"])


def test_health_still_answers_when_ollama_is_down(make_api: MakeApi) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    response = make_api(ollama=down).client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "down"


def test_stats(make_api: MakeApi) -> None:
    api = make_api()
    body = api.client.get("/stats").json()
    assert body["notes"] == 10
    assert body["chunks"] == body["points"] == api.env.store.count()
    assert body["duplicate_groups"] == 0 and body["concepts"] == 3
    assert body["last_sync"] is not None


# --- /search -----------------------------------------------------------------------------------


def test_search_returns_notes_chunks_and_related(make_api: MakeApi) -> None:
    api = make_api(confidence_threshold=0.5)
    body = api.client.post("/search", json={"query": "estrategias"}).json()
    first = body["notes"][0]
    assert first["path"] == CARRERA and first["title"] == "Condiciones de carrera"
    assert first["asignatura"] == "SISTEMAS OPERATIVOS" and first["curso"] == "1º"
    assert first["chunks"][0]["text"] and first["chunks"][0]["heading_path"]
    assert {r["path"] for r in body["related"]} == {SEMAFOROS, ENLACES}
    assert body["related"][0]["via"] == ["semaforo"]
    assert body["top_similarity"] == 0.5 and body["confidence"] == "alta"


def test_search_can_skip_the_graph_and_limit_the_notes(make_api: MakeApi) -> None:
    body = make_api().client.post("/search", json={"query": "de", "k": 2, "graph": False}).json()
    assert len(body["notes"]) <= 2 and body["related"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "x", "k": 0},
        {"query": "x", "k": 100},
        {"k": 3},
        {"query": "x" * 2001},
    ],
)
def test_search_validates_its_input(make_api: MakeApi, payload: dict[str, Any]) -> None:
    assert make_api().client.post("/search", json=payload).status_code == 422


class Failing:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult:
        raise self.exc


def test_search_says_how_to_start_ollama_when_it_is_down(make_api: MakeApi) -> None:
    api = make_api(retriever=Failing(httpx.ConnectError("x")))
    response = api.client.post("/search", json={"query": "x"})
    assert response.status_code == 503
    assert "ollama serve" in response.json()["detail"]


def test_search_says_how_to_start_qdrant_when_it_is_down(make_api: MakeApi) -> None:
    api = make_api(retriever=Failing(ResponseHandlingException(httpx.ConnectError("x"))))
    response = api.client.post("/search", json={"query": "x"})
    assert response.status_code == 503
    assert "tasks.ps1 up" in response.json()["detail"]


# --- /ask (SSE) -------------------------------------------------------------------------------


def test_ask_streams_sources_tokens_and_done(make_api: MakeApi) -> None:
    response = make_api(confidence_threshold=0.5).client.post(
        "/ask", json={"question": "estrategias"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = sse(response.text)
    names = [n for n, _ in events]
    assert names[0] == "sources" and names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    done = events[-1][1]
    text = "".join(d["text"] for n, d in events if n == "token")
    assert text == done["answer"] == "Hay tres estrategias [S1]."
    assert [c["path"] for c in done["citations"]] == [CARRERA]
    assert done["warnings"] == [] and done["not_found"] is False
    assert done["timings"]["total_ms"] > 0


def test_ask_lists_the_citable_sources_first(make_api: MakeApi) -> None:
    events = sse(make_api().client.post("/ask", json={"question": "estrategias"}).text)
    sources = events[0][1]["sources"]
    assert (sources[0]["label"], sources[0]["kind"]) == ("Condiciones de carrera", "evidence")
    assert {s["kind"] for s in sources} == {"evidence", "hint"}


def test_ask_never_streams_an_unverified_citation(make_api: MakeApi) -> None:
    api = make_api(["Dato [S", "9] y [S1]."])
    events = sse(api.client.post("/ask", json={"question": "estrategias"}).text)
    text = "".join(d["text"] for n, d in events if n == "token")
    assert "[S9" not in text and "[cita no verificada: S9]" in text
    assert events[-1][1]["invalid"] == ["S9"]


def test_ask_reports_model_failures_as_an_error_event(make_api: MakeApi) -> None:
    api = make_api()
    api.llm.fail_after = 0
    events = sse(api.client.post("/ask", json={"question": "estrategias"}).text)
    assert events[-1][0] == "error" and "ollama serve" in events[-1][1]["message"]


def test_ask_validates_its_input(make_api: MakeApi) -> None:
    api = make_api()
    assert api.client.post("/ask", json={"question": ""}).status_code == 422
    assert api.client.post("/ask", json={"question": "x", "k": 0}).status_code == 422


# --- /notes -------------------------------------------------------------------------------------


def test_note_content_metadata_and_neighbours(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/notes/{CARRERA}").json()
    assert body["path"] == CARRERA and body["title"] == "Condiciones de carrera"
    assert body["asignatura"] == "SISTEMAS OPERATIVOS" and body["curso"] == "1º"
    assert body["frontmatter"]["conceptos_menores"] == ["exclusión mutua", "sección crítica"]
    assert body["tags"] == ["concurrencia", "hilos"]
    assert body["concepts"] == ["condicion de carrera", "semaforo"]
    assert body["body"].lstrip().startswith("# Condiciones de carrera")
    assert {n["path"] for n in body["related"]} == {SEMAFOROS, ENLACES}


def test_a_utf16_note_is_served_decoded(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/notes/{README}").json()
    assert "Guía del proyecto DIS" in body["body"]


@pytest.mark.parametrize(
    "path",
    ["_conceptos/semaforo.md", "no/existe.md", "../secreto.md", "..%2F..%2Fsecreto.md", "x.png"],
)
def test_notes_outside_the_index_are_not_served(make_api: MakeApi, path: str) -> None:
    assert make_api().client.get(f"/notes/{path}").status_code in (400, 404)


# --- /graph/neighbors -------------------------------------------------------------------------


def test_graph_neighbours_with_concept_statistics(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/graph/neighbors/{CARRERA}").json()
    assert body["path"] == CARRERA
    concepts = {c["name"]: c for c in body["concepts"]}
    assert concepts["semaforo"]["notes"] == 3 and concepts["semaforo"]["idf"] > 0
    assert {n["path"] for n in body["neighbors"]} == {SEMAFOROS, ENLACES}
    assert body["neighbors"][0]["via"] == ["semaforo"]


def test_graph_neighbours_respect_the_limit_and_404_for_unknown(make_api: MakeApi) -> None:
    api = make_api()
    assert len(api.client.get(f"/graph/neighbors/{CARRERA}?limit=1").json()["neighbors"]) == 1
    assert api.client.get("/graph/neighbors/no/existe.md").status_code == 404
    assert api.client.get(f"/graph/neighbors/{CARRERA}?limit=0").status_code == 422


# --- /reindex ---------------------------------------------------------------------------------


def wait_for_state(client: TestClient, wanted: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status: dict[str, Any] = client.get("/reindex/status").json()
        if status["state"] == wanted:
            return status
        time.sleep(0.02)
    raise AssertionError(f"el estado no llegó a {wanted}")


def test_reindex_is_idle_before_the_first_run(make_api: MakeApi) -> None:
    assert make_api().client.get("/reindex/status").json()["state"] == "idle"


def test_reindex_runs_in_the_background_and_reports_the_result(make_api: MakeApi) -> None:
    client = make_api().client
    response = client.post("/reindex")
    assert response.status_code == 202
    done = wait_for_state(client, "done")
    assert done["total"] == 10 and done["done"] == 10
    assert done["report"] == {"indexed": 0, "unchanged": 10, "empty": 0, "deleted": 0, "failed": []}


def test_a_second_reindex_while_running_is_a_conflict(make_api: MakeApi) -> None:
    release = threading.Event()

    def slow(progress: Any) -> SyncReport:
        release.wait(5)
        return SyncReport()

    client = make_api(reindex_run=slow).client
    assert client.post("/reindex").status_code == 202
    response = client.post("/reindex")
    assert response.status_code == 409 and "en marcha" in response.json()["detail"]
    release.set()
    wait_for_state(client, "done")


def test_a_failed_reindex_shows_its_error(make_api: MakeApi) -> None:
    def boom(progress: Any) -> SyncReport:
        raise RuntimeError("Qdrant no responde")

    client = make_api(reindex_run=boom).client
    client.post("/reindex")
    assert "Qdrant no responde" in wait_for_state(client, "error")["error"]


# --- seguridad y documentación ------------------------------------------------------------------


def test_requests_with_a_foreign_host_header_are_rejected(make_api: MakeApi) -> None:
    client = make_api().client
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/health", headers={"host": "127.0.0.1:8000"}).status_code == 200


def test_cors_is_closed_by_default(make_api: MakeApi) -> None:
    response = make_api().client.get("/health", headers={"origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_only_the_configured_origins(make_api: MakeApi) -> None:
    client = make_api(api_cors_origins=["http://localhost:5173"]).client
    ok = client.get("/health", headers={"origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/health", headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_documents_every_endpoint(make_api: MakeApi) -> None:
    paths = make_api().client.get("/openapi.json").json()["paths"]
    for path in ("/health", "/stats", "/search", "/ask", "/notes/{path}", "/reindex",
                 "/reindex/status", "/graph/neighbors/{path}"):  # fmt: skip
        assert path in paths, path


def test_ask_reports_infrastructure_failures_as_an_error_event(make_api: MakeApi) -> None:
    api = make_api(retriever=Failing(httpx.ConnectError("x")))
    response = api.client.post("/ask", json={"question": "x"})
    assert response.status_code == 200  # el flujo ya había empezado: el fallo va como evento
    events = sse(response.text)
    assert events[-1][0] == "error" and "ollama serve" in events[-1][1]["message"]


def test_stats_does_not_run_the_full_health_check(make_api: MakeApi) -> None:
    calls: list[int] = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return ollama_ok(request)

    make_api(ollama=counting).client.get("/stats")
    assert calls == []


def test_a_weak_match_is_flagged_as_low_confidence_by_default(make_api: MakeApi) -> None:
    # El store de pruebas devuelve una similitud de 0,5, por debajo del umbral calibrado (0,6).
    body = make_api().client.post("/search", json={"query": "estrategias"}).json()
    assert body["top_similarity"] == 0.5 and body["confidence"] == "baja"
    events = sse(make_api().client.post("/ask", json={"question": "estrategias"}).text)
    assert "confianza_baja" in events[-1][1]["warnings"]
    assert events[0][1]["confidence"] == "baja"


# --- precalentamiento -------------------------------------------------------------------------


def test_startup_warms_up_the_search_in_the_background(make_api: MakeApi) -> None:
    import threading

    called = threading.Event()
    api = make_api(warmup=called.set)
    with api.client:
        assert called.wait(timeout=5)


def test_a_failed_warmup_does_not_stop_the_api(make_api: MakeApi) -> None:
    import threading

    tried = threading.Event()

    def broken() -> None:
        tried.set()
        raise httpx.ConnectError("Ollama no responde")

    api = make_api(warmup=broken)
    with api.client:
        assert tried.wait(timeout=5)
        assert api.client.get("/health").status_code == 200


# --- interfaz web (frontend/dist) ---------------------------------------------------------------


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>Segundo cerebro</title>", encoding="utf-8")
    (d / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (d / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no se sirve", encoding="utf-8")
    return d


def test_the_app_is_served_at_the_root(make_api: MakeApi, dist: Path) -> None:
    r = make_api(static_dir=dist).client.get("/")
    assert r.status_code == 200 and "Segundo cerebro" in r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_for_a_year(make_api: MakeApi, dist: Path) -> None:
    r = make_api(static_dir=dist).client.get("/assets/app-abc123.js")
    assert r.status_code == 200 and "console.log" in r.text
    assert "immutable" in r.headers["cache-control"]


def test_other_files_of_the_build_are_served(make_api: MakeApi, dist: Path) -> None:
    r = make_api(static_dir=dist).client.get("/favicon.svg")
    assert r.status_code == 200 and r.text == "<svg/>"


@pytest.mark.parametrize("route", ["/estado", "/preguntar/algo", "/estado/"])
def test_unknown_browser_routes_fall_back_to_the_app(
    make_api: MakeApi, dist: Path, route: str
) -> None:
    r = make_api(static_dir=dist).client.get(route)
    assert r.status_code == 200 and "Segundo cerebro" in r.text


@pytest.mark.parametrize(
    "route", ["/notes/no/existe.md", "/graph/neighbors/x.md", "/asset/falta.js", "/assets/falta.js"]
)
def test_api_and_missing_asset_paths_never_fall_back_to_the_app(
    make_api: MakeApi, dist: Path, route: str
) -> None:
    r = make_api(static_dir=dist).client.get(route)
    assert r.status_code == 404 and "<title>" not in r.text


def test_the_api_keeps_working_next_to_the_app(make_api: MakeApi, dist: Path) -> None:
    api = make_api(static_dir=dist)
    assert api.client.get("/health").status_code == 200
    assert api.client.get("/stats").status_code == 200


@pytest.mark.parametrize(
    "route",
    ["/../secreto.txt", "/..%2fsecreto.txt", "/%2e%2e/secreto.txt", "/assets/../../secreto.txt"],
)
def test_it_does_not_serve_files_outside_the_build(
    make_api: MakeApi, dist: Path, route: str
) -> None:
    r = make_api(static_dir=dist).client.get(route)
    assert "no se sirve" not in r.text


def test_only_get_falls_back_to_the_app(make_api: MakeApi, dist: Path) -> None:
    assert make_api(static_dir=dist).client.post("/estado").status_code in (404, 405)


def test_without_a_build_the_root_explains_how_to_make_one(
    make_api: MakeApi, tmp_path: Path
) -> None:
    r = make_api(static_dir=tmp_path / "no-hay").client.get("/")
    assert r.status_code == 404
    r = make_api().client.get("/")
    assert r.status_code == 404


# --- filtros y facetas de /search, y /subjects ---------------------------------------------------


def _facet(body: dict[str, Any], name: str) -> dict[str, int]:
    return {f["value"]: f["count"] for f in body["facets"][name]}


def test_search_returns_facets_with_canonical_subjects(make_api: MakeApi) -> None:
    body = make_api().client.post("/search", json={"query": "estrategias"}).json()
    assert _facet(body, "asignaturas") == {"SISTEMAS OPERATIVOS": 1}
    assert _facet(body, "cursos") == {"1º": 1}


def test_search_filters_by_subject_ignoring_case_and_accents(make_api: MakeApi) -> None:
    body = (
        make_api()
        .client.post(
            "/search", json={"query": "estrategias", "asignaturas": ["sistemas operativos"]}
        )
        .json()
    )
    assert [n["path"] for n in body["notes"]] == [CARRERA]


def test_search_filters_are_anded_across_facets_and_keep_the_alternatives(
    make_api: MakeApi,
) -> None:
    body = (
        make_api()
        .client.post(
            "/search",
            json={"query": "estrategias", "asignaturas": ["SISTEMAS OPERATIVOS"], "cursos": ["4º"]},
        )
        .json()
    )
    assert body["notes"] == []
    assert _facet(body, "asignaturas")["SISTEMAS OPERATIVOS"] == 1  # lo que habría sin el filtro
    assert _facet(body, "cursos")["4º"] == 0  # el valor elegido se puede desmarcar


def test_search_filters_by_tag(make_api: MakeApi) -> None:
    api = make_api()
    tags = _facet(api.client.post("/search", json={"query": "estrategias"}).json(), "tags")
    assert tags, "la nota de ejemplo tiene etiquetas"
    some = next(iter(tags))
    body = api.client.post("/search", json={"query": "estrategias", "tags": [some]}).json()
    assert [n["path"] for n in body["notes"]] == [CARRERA]
    other = api.client.post("/search", json={"query": "estrategias", "tags": ["no-existe"]}).json()
    assert other["notes"] == []


def test_search_validates_the_filters(make_api: MakeApi) -> None:
    api = make_api()
    assert (
        api.client.post("/search", json={"query": "x", "asignaturas": "no-es-lista"}).status_code
        == 422
    )
    too_many = {"query": "x", "tags": [f"t{i}" for i in range(60)]}
    assert api.client.post("/search", json=too_many).status_code == 422


def test_subjects_lists_the_canonical_subjects_with_their_notes(make_api: MakeApi) -> None:
    body = make_api().client.get("/subjects").json()
    by_name = {s["name"]: s["notes"] for s in body}
    assert by_name["SISTEMAS OPERATIVOS"] == 2
    assert [s["name"].casefold() for s in body] == sorted(s["name"].casefold() for s in body)


# --- enlaces resueltos, notas que enlazan y Obsidian en /notes ---------------------------


def test_a_note_comes_with_its_links_resolved_to_candidate_notes(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/notes/{ENLACES}").json()
    resolved = body["resolved_links"]
    assert set(resolved) == set(body["links"])
    assert resolved["Semáforos y monitores"] == [SEMAFOROS]
    assert all(isinstance(v, list) for v in resolved.values())


def test_a_link_to_a_missing_note_resolves_to_nothing(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/notes/{ENLACES}").json()
    missing = [t for t, found in body["resolved_links"].items() if not found]
    assert missing  # la nota de ejemplo enlaza a notas que no existen


def test_notes_that_link_here_are_listed_as_backlinks(make_api: MakeApi) -> None:
    body = make_api().client.get(f"/notes/{SEMAFOROS}").json()
    assert ENLACES in [b["path"] for b in body["backlinks"]]
    assert all(set(b) == {"path", "title"} for b in body["backlinks"])


def test_a_note_comes_with_its_obsidian_link(make_api: MakeApi) -> None:
    body = make_api(obsidian_vault="Cerebro").client.get(f"/notes/{CARRERA}").json()
    assert body["obsidian_url"].startswith("obsidian://open?vault=Cerebro&file=1%C2%BA%2FSISTEMAS")
    assert body["obsidian_url"].endswith("Condiciones%20de%20carrera")


@pytest.mark.parametrize(
    "route",
    [
        "/nota/3%C2%BA/Redes/Tema%201.md",
        "/nota/a/b/c.v2.md",
        "/nota/x.md?p=3",
        "/buscar?q=algo.pdf",
    ],
)
def test_a_note_url_reloaded_in_the_browser_still_opens_the_app(
    make_api: MakeApi, dist: Path, route: str
) -> None:
    # Regresión: una ruta de nota termina en «.md» y se tomaba por un fichero que falta (404).
    r = make_api(static_dir=dist).client.get(route)
    assert r.status_code == 200 and "Segundo cerebro" in r.text


@pytest.mark.parametrize(
    "route", ["/falta.js", "/x/falta.css", "/img/falta.png", "/f.woff2", "/robots.txt", "/a.map"]
)
def test_missing_static_files_are_404_not_the_app(
    make_api: MakeApi, dist: Path, route: str
) -> None:
    r = make_api(static_dir=dist).client.get(route)
    assert r.status_code == 404 and "<title>" not in r.text
