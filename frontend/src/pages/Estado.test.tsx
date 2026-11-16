import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionContext } from "../hooks/session";
import { ApiError, type DoneEvent, type HealthReport, type ReindexStatus, type Stats } from "../lib/api";
import { Estado } from "./Estado";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiGet,
  apiPost,
}));

const health: HealthReport = {
  status: "ok",
  ollama: {
    ok: true,
    version: "0.12.3",
    models: { "qwen2.5:7b": true, "bge-m3": true },
    loaded: [{ name: "qwen2.5:7b", vram_mib: 4915, expires_at: null }],
    error: null,
  },
  qdrant: { ok: true, points: 12345, error: null },
  vault: { ok: true, path: "C:\\ruta\\a\\tu\\vault" },
  gpu: { used_mib: 5120, total_mib: 8192 },
  hints: [],
};

const stats: Stats = { notes: 1000, chunks: 12000, points: 12345, duplicate_groups: 7, concepts: 300, last_sync: null };

const idle: ReindexStatus = {
  state: "idle",
  done: 0,
  total: 0,
  current: null,
  started_at: null,
  finished_at: null,
  report: null,
  error: null,
};

function routes(over: Record<string, unknown> = {}) {
  const table: Record<string, unknown> = { "/health": health, "/stats": stats, "/reindex/status": idle, ...over };
  apiGet.mockImplementation(async (path: string) => {
    const value = table[path];
    if (value instanceof Error) throw value;
    return value;
  });
}

const done = (total_ms: number): DoneEvent =>
  ({
    type: "done",
    answer: "",
    citations: [],
    invalid: [],
    bad_pages: [],
    warnings: [],
    not_found: false,
    confidence: "alta",
    similarity: 0.7,
    timings: { retrieval_ms: 1, first_token_ms: 1, total_ms, llm_load_ms: 0, tokens_per_second: 40 },
    prompt_tokens: 1,
    completion_tokens: 1,
  }) satisfies DoneEvent;

function setup(entries: DoneEvent[] = []) {
  return render(
    <SessionContext.Provider value={{ entries, record: vi.fn() }}>
      <Estado />
    </SessionContext.Provider>,
  );
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("Estado", () => {
  it("shows a loading state and then the services", async () => {
    routes();
    setup();
    expect(screen.getByRole("status")).toHaveTextContent("Comprobando servicios");
    expect(await screen.findByRole("heading", { name: "Ollama" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Qdrant" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vault" })).toBeInTheDocument();
  });

  it("states each service in words, not only with colour", async () => {
    routes();
    setup();
    const ollama = (await screen.findByRole("heading", { name: "Ollama" })).closest("section")!;
    expect(within(ollama).getByText("Funciona")).toBeInTheDocument();
    expect(within(ollama).getAllByText(/qwen2\.5:7b/).length).toBeGreaterThan(0);
    expect(within(ollama).getByText(/versión 0\.12\.3/)).toBeInTheDocument();
  });

  it("shows the GPU memory as a progress bar with a text value", async () => {
    routes();
    setup();
    const bar = await screen.findByRole("progressbar", { name: "Memoria de la GPU" });
    expect(bar).toHaveAttribute("aria-valuenow", "5120");
    expect(bar).toHaveAttribute("aria-valuemax", "8192");
    expect(bar).toHaveAttribute("aria-valuetext", "5,0 GiB de 8,0 GiB");
  });

  it("shows the index figures with thousands separators", async () => {
    routes();
    setup();
    await screen.findByRole("heading", { name: "Ollama" });
    expect(screen.getByText("12.000")).toBeInTheDocument();
    expect(screen.getByText("1000".replace(/(\d)(\d{3})/, "$1.$2"))).toBeInTheDocument();
  });

  it("explains a service that is down and offers its command to copy", async () => {
    routes({
      "/health": {
        ...health,
        status: "degraded",
        ollama: { ...health.ollama, ok: false, error: "No responde" },
        hints: ["Arranca Ollama con `ollama serve`."],
      },
    });
    setup();
    const ollama = (await screen.findByRole("heading", { name: "Ollama" })).closest("section")!;
    expect(within(ollama).getByText("No responde")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar el comando: ollama serve" })).toBeInTheDocument();
  });

  it("shows the API being unreachable as an alert", async () => {
    routes({ "/health": new ApiError(0, "No se puede conectar con la API. Ejecuta `brain serve`.") });
    setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("No se puede conectar con la API");
  });

  it("shows the median latency of this session, or says there is none yet", async () => {
    routes();
    const first = setup();
    expect(await screen.findByText(/Aún no hay respuestas en esta sesión/)).toBeInTheDocument();
    first.unmount();
    routes();
    setup([done(1000), done(3000), done(2000)]);
    expect(await screen.findByText("2,0 s")).toBeInTheDocument();
    expect(screen.getByText(/mediana de 3 respuestas/)).toBeInTheDocument();
  });

  it("starts a reindex and shows its progress", async () => {
    routes();
    apiPost.mockResolvedValue({ ...idle, state: "running", done: 0, total: 10 });
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Reindexar ahora" }));
    expect(apiPost).toHaveBeenCalledWith("/reindex", undefined);
    routes({ "/reindex/status": { ...idle, state: "running", done: 4, total: 10, current: "a/Nota.md" } });
    const bar = await screen.findByRole("progressbar", { name: "Progreso del reindexado" });
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuenow", "4"), { timeout: 4000 });
    expect(screen.getByRole("button", { name: /Reindexando/ })).toBeDisabled();
  });

  it("explains that a reindex is already running (409)", async () => {
    routes();
    apiPost.mockRejectedValue(new ApiError(409, "Ya hay un reindexado en marcha."));
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Reindexar ahora" }));
    expect(await screen.findByText("Ya hay un reindexado en marcha.")).toBeInTheDocument();
  });

  it("summarises a finished reindex", async () => {
    routes({
      "/reindex/status": {
        ...idle,
        state: "done",
        finished_at: new Date().toISOString(),
        report: { indexed: 3, unchanged: 990, empty: 2, deleted: 1, failed: [] },
      },
    });
    setup();
    expect(await screen.findByText(/3 indexadas/)).toBeInTheDocument();
    expect(screen.getByText(/990 sin cambios/)).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    routes();
    const { container } = setup([done(1500)]);
    await screen.findByRole("heading", { name: "Ollama" });
    await waitFor(async () => expect(await axe(container)).toHaveNoViolations());
  });
});
