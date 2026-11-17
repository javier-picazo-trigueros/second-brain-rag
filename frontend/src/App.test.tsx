import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

const askStream = vi.hoisted(() => vi.fn());
vi.mock("./lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./lib/api")>()),
  apiGet: vi.fn(() => new Promise(() => {})),
  askStream,
}));

describe("App", () => {
  it("shows Preguntar at the root", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
  });

  it("shows Estado at /estado", () => {
    render(
      <MemoryRouter initialEntries={["/estado"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Estado" })).toBeInTheDocument();
  });

  it("falls back to Preguntar on an unknown path", () => {
    render(
      <MemoryRouter initialEntries={["/nada"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
  });
});

describe("conversation across screens", () => {
  it("keeps the question and the answer when going to Estado and back, and lists it in the history", async () => {
    askStream.mockImplementation(async function* () {
      yield { type: "sources", sources: [], fragments: [], confidence: "alta", similarity: 0.7, dropped_notes: 0 };
      yield {
        type: "done",
        answer: "Respuesta guardada",
        citations: [],
        invalid: [],
        warnings: [],
        not_found: false,
        confidence: "alta",
        similarity: 0.7,
        timings: { retrieval_ms: 1, first_token_ms: 1, total_ms: 2, llm_load_ms: 0, tokens_per_second: 40 },
        prompt_tokens: 1,
        completion_tokens: 1,
      };
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Tu pregunta" }), "¿Qué es un grafo?{Enter}");
    expect(await screen.findByText("Respuesta guardada")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "Estado" }));
    expect(screen.getByRole("heading", { name: "Estado" })).toBeInTheDocument();
    const history = screen.getByRole("region", { name: "Esta sesión" });
    expect(history).toHaveTextContent("¿Qué es un grafo?");

    await userEvent.click(screen.getByRole("link", { name: "Preguntar" }));
    expect(screen.getByText("Respuesta guardada")).toBeInTheDocument();
    expect(screen.getAllByText("¿Qué es un grafo?").length).toBeGreaterThan(0);
  });
});

describe("new conversation", () => {
  it("clears the thread and the history", async () => {
    askStream.mockImplementation(async function* () {
      yield { type: "sources", sources: [], fragments: [], confidence: "alta", similarity: 0.7, dropped_notes: 0 };
      yield {
        type: "done", answer: "Respuesta antigua", citations: [], invalid: [], warnings: [], not_found: false,
        confidence: "alta", similarity: 0.7,
        timings: { retrieval_ms: 1, first_token_ms: 1, total_ms: 2, llm_load_ms: 0, tokens_per_second: 40 },
        prompt_tokens: 1, completion_tokens: 1,
      };
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Tu pregunta" }), "Algo{Enter}");
    expect(await screen.findByText("Respuesta antigua")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Nueva conversación" }));
    expect(screen.queryByText("Respuesta antigua")).toBeNull();
    expect(screen.queryByRole("region", { name: "Esta sesión" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
  });
});
