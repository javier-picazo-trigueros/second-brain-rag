from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
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
        deltas: Sequence[str] = ("Hay tres estrategias ", "[[Condiciones de carrera]]."),
        *,
        retriever: Any = None,
        reindex_run: Callable[..., SyncReport] | None = None,
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
            retriever=used,
            pipeline=AnswerPipeline(s, used, llm),
            manifest=env.manifest,
            health=health.check,
            reindex=reindex,
            points=env.store.count,
        )
        return Api(TestClient(create_app(services), base_url="http://localhost"), env, llm)

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
    assert text == done["answer"] == "Hay tres estrategias [[Condiciones de carrera]]."
    assert [c["path"] for c in done["citations"]] == [CARRERA]
    assert done["warnings"] == [] and done["not_found"] is False
    assert done["timings"]["total_ms"] > 0


def test_ask_lists_the_citable_sources_first(make_api: MakeApi) -> None:
    events = sse(make_api().client.post("/ask", json={"question": "estrategias"}).text)
    sources = events[0][1]["sources"]
    assert (sources[0]["label"], sources[0]["kind"]) == ("Condiciones de carrera", "evidence")
    assert {s["kind"] for s in sources} == {"evidence", "hint"}


def test_ask_never_streams_an_unverified_citation(make_api: MakeApi) -> None:
    api = make_api(["Dato [[Inve", "ntada]] y [[Condiciones de carrera]]."])
    events = sse(api.client.post("/ask", json={"question": "estrategias"}).text)
    text = "".join(d["text"] for n, d in events if n == "token")
    assert "[[Inventada" not in text and "[cita no verificada: Inventada]" in text
    assert events[-1][1]["invalid"] == ["Inventada"]


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
