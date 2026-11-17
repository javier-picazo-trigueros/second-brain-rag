import { describe, expect, it } from "vitest";

import type { AskEvent, DoneEvent, SourcesEvent } from "../lib/api";
import { askReducer, initialAskState, type AskState } from "./askState";

const sources: SourcesEvent = {
  type: "sources",
  sources: [
    {
      label: "Semáforos",
      path: "1º/SO/Semáforos.md",
      title: "Semáforos",
      kind: "evidence",
      pages: [7],
      asignatura: "SISTEMAS",
      curso: "1º",
      truncated: false,
    },
  ],
  confidence: "alta",
  similarity: 0.7,
  dropped_notes: 0,
};

const done: DoneEvent = {
  type: "done",
  answer: "Hola mundo",
  citations: [],
  invalid: [],
  bad_pages: [],
  warnings: [],
  not_found: false,
  confidence: "alta",
  similarity: 0.7,
  timings: { retrieval_ms: 10, first_token_ms: 20, total_ms: 30, llm_load_ms: 0, tokens_per_second: 45 },
  prompt_tokens: 100,
  completion_tokens: 5,
};

function run(events: AskEvent[], from: AskState = askReducer(initialAskState, { type: "start", question: "¿Q?" })) {
  return events.reduce<AskState>((state, event) => askReducer(state, event), from);
}

describe("askReducer", () => {
  it("starts idle", () => {
    expect(initialAskState.status).toBe("idle");
  });

  it("start puts the question in flight and clears the previous answer", () => {
    const state = askReducer(run([sources, { type: "token", text: "a" }, done]), {
      type: "start",
      question: "otra",
    });
    expect(state).toMatchObject({ status: "waiting", question: "otra", text: "", sources: [], done: null });
  });

  it("sources move to streaming and keep the confidence", () => {
    const state = run([sources]);
    expect(state.status).toBe("streaming");
    expect(state.sources).toHaveLength(1);
    expect(state.confidence).toBe("alta");
  });

  it("tokens accumulate the text in order", () => {
    const state = run([sources, { type: "token", text: "Hola " }, { type: "token", text: "mundo" }]);
    expect(state.text).toBe("Hola mundo");
  });

  it("done finishes with the final answer, which wins over the streamed text", () => {
    const state = run([sources, { type: "token", text: "Hola" }, done]);
    expect(state.status).toBe("done");
    expect(state.text).toBe("Hola mundo");
    expect(state.done).toBe(done);
  });

  it("an error keeps what was already streamed and records the message", () => {
    const state = run([sources, { type: "token", text: "Hola" }, { type: "error", message: "Ollama no responde" }]);
    expect(state).toMatchObject({ status: "error", text: "Hola", error: "Ollama no responde" });
  });

  it("an error before any source is still an error", () => {
    expect(run([{ type: "error", message: "x" }])).toMatchObject({ status: "error", text: "" });
  });

  it("stop returns to done-or-idle without losing the partial text", () => {
    const streaming = run([sources, { type: "token", text: "Hola" }]);
    const stopped = askReducer(streaming, { type: "stop" });
    expect(stopped).toMatchObject({ status: "stopped", text: "Hola" });
  });

  it("stop before anything arrived leaves an empty stopped state", () => {
    expect(askReducer(askReducer(initialAskState, { type: "start", question: "q" }), { type: "stop" })).toMatchObject({
      status: "stopped",
      text: "",
    });
  });

  it("ignores late events after the user stopped", () => {
    const stopped = askReducer(run([sources, { type: "token", text: "Hola" }]), { type: "stop" });
    expect(askReducer(stopped, { type: "token", text: " tarde" }).text).toBe("Hola");
    expect(askReducer(stopped, done).status).toBe("stopped");
  });

  it("reset goes back to idle", () => {
    expect(askReducer(run([sources, done]), { type: "reset" })).toEqual(initialAskState);
  });

  it("a failed request (not an SSE error) is recorded with its message", () => {
    const state = askReducer(askReducer(initialAskState, { type: "start", question: "q" }), {
      type: "failed",
      message: "No se puede conectar con la API",
    });
    expect(state).toMatchObject({ status: "error", error: "No se puede conectar con la API" });
  });
});
