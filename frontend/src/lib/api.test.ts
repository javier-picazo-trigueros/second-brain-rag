import { describe, expect, it, vi } from "vitest";

import { ApiError, apiGet, apiPost, askStream, type AskEvent } from "./api";

const encoder = new TextEncoder();

function sseResponse(text: string, status = 200): Response {
  return new Response(encoder.encode(text), {
    status,
    headers: { "content-type": "text/event-stream" },
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function collect(iterable: AsyncIterable<AskEvent>): Promise<AskEvent[]> {
  const out: AskEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

describe("apiGet / apiPost", () => {
  it("returns the parsed JSON body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ notes: 3 }));
    expect(await apiGet("/stats", { fetchImpl })).toEqual({ notes: 3 });
    expect(fetchImpl).toHaveBeenCalledWith("/stats", expect.objectContaining({ method: "GET" }));
  });

  it("sends JSON on POST", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ ok: true }, 202));
    await apiPost("/reindex", undefined, { fetchImpl });
    expect(fetchImpl).toHaveBeenCalledWith("/reindex", expect.objectContaining({ method: "POST" }));
  });

  it("turns an HTTP error into an ApiError carrying the server's detail", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Ollama no responde en http://x" }, 503));
    const error = await apiGet("/health", { fetchImpl }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toBe("Ollama no responde en http://x");
  });

  it("explains how to start the API when it cannot be reached", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await apiGet("/health", { fetchImpl }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toMatch(/brain serve/);
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("boom", { status: 500, statusText: "Internal" }));
    const error = await apiGet("/x", { fetchImpl }).catch((e: unknown) => e);
    expect((error as ApiError).message).toMatch(/500/);
  });
});

describe("askStream", () => {
  const body =
    'event: sources\ndata: {"sources":[],"confidence":"alta","similarity":0.7,"dropped_notes":0}\n\n' +
    'event: token\ndata: {"text":"Hola "}\n\n' +
    'event: token\ndata: {"text":"mundo"}\n\n' +
    'event: done\ndata: {"answer":"Hola mundo","citations":[],"invalid":[],"bad_pages":[],' +
    '"warnings":[],"not_found":false,"confidence":"alta","similarity":0.7,' +
    '"timings":{"retrieval_ms":1,"first_token_ms":2,"total_ms":3,"llm_load_ms":0,"tokens_per_second":50},' +
    '"prompt_tokens":10,"completion_tokens":2}\n\n';

  it("yields typed events in order", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(body));
    const events = await collect(askStream("¿Hola?", { fetchImpl }));
    expect(events.map((e) => e.type)).toEqual(["sources", "token", "token", "done"]);
    expect(events[1]).toEqual({ type: "token", text: "Hola " });
    const done = events[3]!;
    expect(done.type === "done" && done.answer).toBe("Hola mundo");
  });

  it("posts the question as JSON", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(body));
    await collect(askStream("¿Qué es?", { fetchImpl }));
    const init = fetchImpl.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ question: "¿Qué es?" });
  });

  it("forwards the abort signal", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse(body));
    const controller = new AbortController();
    await collect(askStream("x", { fetchImpl, signal: controller.signal }));
    expect((fetchImpl.mock.calls[0]![1] as RequestInit).signal).toBe(controller.signal);
  });

  it("surfaces server-sent errors as an error event", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(sseResponse('event: error\ndata: {"message":"Ollama no responde"}\n\n'));
    const events = await collect(askStream("x", { fetchImpl }));
    expect(events).toEqual([{ type: "error", message: "Ollama no responde" }]);
  });

  it("ignores events it does not know", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse('event: otro\ndata: {}\n\n' + body));
    const events = await collect(askStream("x", { fetchImpl }));
    expect(events.map((e) => e.type)).toEqual(["sources", "token", "token", "done"]);
  });

  it("throws an ApiError when the request itself fails", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: "Pregunta no válida" }, 422));
    await expect(collect(askStream("x", { fetchImpl }))).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
    });
  });

  it("reports a malformed event as an error instead of crashing", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(sseResponse("event: token\ndata: {roto\n\n"));
    const events = await collect(askStream("x", { fetchImpl }));
    expect(events[0]).toMatchObject({ type: "error" });
  });
});
