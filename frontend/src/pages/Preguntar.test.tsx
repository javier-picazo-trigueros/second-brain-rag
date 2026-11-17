import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationProvider } from "../hooks/conversation";
import { NoteContext } from "../hooks/notePanel";
import { SessionContext } from "../hooks/session";
import {
  ApiError,
  type AskEvent,
  type DoneEvent,
  type FragmentInfo,
  type SourceInfo,
  type SourcesEvent,
} from "../lib/api";
import { Preguntar } from "./Preguntar";

const askStream = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  askStream,
}));

const source = (label: string, kind: "evidence" | "hint" = "evidence", pages: number[] = []): SourceInfo => ({
  label,
  path: `x/${label}.md`,
  title: label,
  kind,
  pages,
  asignatura: "SISTEMAS",
  curso: "1º",
  truncated: false,
});

const fragments: FragmentInfo[] = [
  { id: "S1", label: "Semáforos", path: "x/Semáforos.md", title: "Semáforos", kind: "evidence", page: 7, heading: null },
  { id: "S2", label: "Redes", path: "x/Redes.md", title: "Redes", kind: "hint", page: null, heading: null },
];

const sourcesEvent = (over: Partial<SourcesEvent> = {}): SourcesEvent => ({
  type: "sources",
  sources: [source("Semáforos", "evidence", [7]), source("Redes", "hint")],
  fragments,
  confidence: "alta",
  similarity: 0.7,
  dropped_notes: 0,
  ...over,
});

const doneEvent = (over: Partial<DoneEvent> = {}): DoneEvent => ({
  type: "done",
  answer: "Un semáforo es un contador [S1].",
  citations: [],
  invalid: [],
  warnings: [],
  not_found: false,
  confidence: "alta",
  similarity: 0.7,
  timings: { retrieval_ms: 100, first_token_ms: 900, total_ms: 2500, llm_load_ms: 0, tokens_per_second: 48 },
  prompt_tokens: 3000,
  completion_tokens: 60,
  ...over,
});

function script(events: AskEvent[]) {
  askStream.mockImplementation(async function* () {
    for (const event of events) yield event;
  });
}

/** Flujo que el test controla paso a paso. */
function controlled() {
  const queue: AskEvent[] = [];
  let wake: (() => void) | null = null;
  let closed = false;
  let signal: AbortSignal | undefined;
  askStream.mockImplementation(async function* (_q: string, options?: { signal?: AbortSignal }) {
    signal = options?.signal;
    while (!closed) {
      while (queue.length > 0) yield queue.shift()!;
      if (closed) break;
      await new Promise<void>((resolve) => {
        wake = resolve;
      });
    }
  });
  return {
    push(event: AskEvent) {
      queue.push(event);
      wake?.();
    },
    close() {
      closed = true;
      wake?.();
    },
    get signal() {
      return signal;
    },
  };
}

const open = vi.fn();
const record = vi.fn();

function setup() {
  return render(
    <MemoryRouter>
      <SessionContext.Provider value={{ entries: [], record }}>
        <NoteContext.Provider value={{ open, close: vi.fn() }}>
          <ConversationProvider>
            <Preguntar />
          </ConversationProvider>
        </NoteContext.Provider>
      </SessionContext.Provider>
    </MemoryRouter>,
  );
}

async function ask(question: string) {
  await userEvent.type(screen.getByRole("textbox", { name: "Tu pregunta" }), `${question}{Enter}`);
}

beforeEach(() => {
  askStream.mockReset();
  open.mockReset();
  record.mockReset();
});

describe("Preguntar: estado inicial", () => {
  it("invites to ask and states, visibly, that each question is independent", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
    expect(screen.getByText(/Cada pregunta se responde de forma independiente/)).toBeInTheDocument();
  });

  it("offers example questions that can be sent with one click", async () => {
    script([sourcesEvent(), doneEvent()]);
    setup();
    const [first] = screen.getAllByRole("button", { name: /^¿/ });
    await userEvent.click(first!);
    expect(askStream).toHaveBeenCalledWith(first!.textContent, expect.anything());
  });
});

describe("Preguntar: respuesta", () => {
  it("shows the question, the streamed answer with clickable citations, sources and details", async () => {
    script([sourcesEvent(), { type: "token", text: "Un semáforo es un contador " }, doneEvent()]);
    setup();
    await ask("¿Qué es un semáforo?");
    expect(await screen.findByText("¿Qué es un semáforo?")).toBeInTheDocument();
    const chips = await screen.findAllByRole("button", { name: /Semáforos/ });
    expect(chips).toHaveLength(2); // el número en el texto y su chip en la fila de fuentes
    await userEvent.click(chips[0]!);
    expect(open).toHaveBeenCalledWith("x/Semáforos.md", 7);
    expect(screen.getByRole("heading", { name: "Fuentes · 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cómo se ha respondido/ })).toBeInTheDocument();
  });

  it("always has a level-one heading, even once the thread has started", async () => {
    script([sourcesEvent(), doneEvent()]);
    setup();
    await ask("¿Hola?");
    await screen.findByRole("button", { name: /Cómo se ha respondido/ });
    expect(screen.getByRole("heading", { level: 1, name: "Preguntar" })).toBeInTheDocument();
  });

  it("announces progress and turns Send into Stop while answering", async () => {
    const flow = controlled();
    setup();
    await ask("¿Hola?");
    expect(await screen.findByRole("status")).toHaveTextContent("Buscando en tus apuntes");
    expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument();
    flow.push(sourcesEvent());
    flow.push({ type: "token", text: "Texto parcial" });
    expect(await screen.findByText("Texto parcial")).toBeInTheDocument();
    expect(screen.getByTestId("answer")).toHaveAttribute("aria-busy", "true");
    flow.push(doneEvent({ answer: "Texto parcial final" }));
    expect(await screen.findByText("Texto parcial final")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeInTheDocument();
    flow.close();
  });

  it("stops the request, keeps the partial text and says so", async () => {
    const flow = controlled();
    setup();
    await ask("¿Hola?");
    flow.push(sourcesEvent());
    flow.push({ type: "token", text: "Mitad de la respuesta" });
    await screen.findByText("Mitad de la respuesta");
    await userEvent.click(screen.getByRole("button", { name: "Parar" }));
    expect(await screen.findByText("Respuesta detenida")).toBeInTheDocument();
    expect(screen.getByText("Mitad de la respuesta")).toBeInTheDocument();
    expect(flow.signal?.aborted).toBe(true);
    flow.close();
  });

  it("records the timings of a finished answer for the Estado screen", async () => {
    const done = doneEvent();
    script([sourcesEvent(), done]);
    setup();
    await ask("¿Hola?");
    await screen.findByRole("button", { name: /Cómo se ha respondido/ });
    expect(record).toHaveBeenCalledWith(done);
  });

  it("keeps earlier questions on screen when asking another one", async () => {
    script([sourcesEvent(), doneEvent({ answer: "Primera respuesta" })]);
    setup();
    await ask("Primera pregunta");
    await screen.findByText("Primera respuesta");
    script([sourcesEvent(), doneEvent({ answer: "Segunda respuesta" })]);
    await ask("Segunda pregunta");
    await screen.findByText("Segunda respuesta");
    expect(screen.getByText("Primera pregunta")).toBeInTheDocument();
    expect(screen.getByText("Primera respuesta")).toBeInTheDocument();
  });
});

describe("Preguntar: avisos", () => {
  it("shows low confidence as a calm chip, never as an alert", async () => {
    script([
      sourcesEvent({ confidence: "baja", similarity: 0.57 }),
      doneEvent({ warnings: ["confianza_baja"], confidence: "baja", similarity: 0.57 }),
    ]);
    setup();
    await ask("¿Algo raro?");
    const notice = await screen.findByTestId("notice");
    expect(notice).toHaveTextContent("Confianza baja");
    expect(notice).toHaveAttribute("data-tone", "neutral");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("marks an unverified citation inline and counts it", async () => {
    script([
      sourcesEvent(),
      doneEvent({
        answer: "Dato [cita no verificada: Inventada] y [S1].",
        warnings: ["citas_no_verificadas"],
        invalid: ["Inventada"],
      }),
    ]);
    setup();
    await ask("¿Dato?");
    expect(await screen.findByRole("note", { name: /cita no verificada: Inventada/i })).toBeInTheDocument();
    expect(screen.getByTestId("notice")).toHaveTextContent("1 cita no verificada");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("presents 'no lo encuentro' as a calm card with the way out", async () => {
    script([
      sourcesEvent({ confidence: "baja", similarity: 0.56 }),
      doneEvent({
        answer: "No lo encuentro en el vault. Podrías mirar: [S1].",
        not_found: true,
        warnings: ["confianza_baja"],
        confidence: "baja",
        similarity: 0.56,
      }),
    ]);
    setup();
    await ask("¿Borrow checker?");
    expect(await screen.findByRole("heading", { name: "No lo encuentro en tus apuntes" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("notice")).toBeNull(); // la tarjeta ya explica la confianza
    expect(screen.getByText(/se parece poco a lo que hay en tus apuntes/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reformular la pregunta" }));
    expect(screen.getByRole("textbox", { name: "Tu pregunta" })).toHaveFocus();
  });

  it("tells the user what to do when the answer was cut", async () => {
    script([sourcesEvent(), doneEvent({ warnings: ["respuesta_truncada"] })]);
    setup();
    await ask("¿Largo?");
    expect(await screen.findByTestId("notice")).toHaveTextContent("Respuesta cortada");
  });

  it("shows service failures as the one red alert, with the command to copy", async () => {
    script([{ type: "error", message: "Ollama no responde en http://x: arráncalo con `ollama serve`." }]);
    setup();
    await ask("¿Hola?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Ollama no responde");
    expect(screen.getByRole("button", { name: "Copiar el comando: ollama serve" })).toBeInTheDocument();
  });

  it("shows an unreachable API as an alert too", async () => {
    // eslint-disable-next-line require-yield
    askStream.mockImplementation(async function* () {
      throw new ApiError(0, "No se puede conectar con la API. ¿Está arrancada? Ejecuta `brain serve`.");
    });
    setup();
    await ask("¿Hola?");
    expect(await screen.findByRole("alert")).toHaveTextContent("No se puede conectar con la API");
  });

  it("reports a stream that ended without finishing", async () => {
    script([sourcesEvent(), { type: "token", text: "Corto" }]);
    setup();
    await ask("¿Hola?");
    expect(await screen.findByRole("alert")).toHaveTextContent(/interrumpida/i);
    expect(screen.getByText("Corto")).toBeInTheDocument();
  });
});

describe("Preguntar: accesibilidad", () => {
  it("has no violations with an answer, notices and sources on screen", async () => {
    script([
      sourcesEvent(),
      doneEvent({ warnings: ["confianza_baja", "citas_no_verificadas"], invalid: ["X"], confidence: "baja" }),
    ]);
    const { container } = setup();
    await ask("¿Hola?");
    await waitFor(() => expect(within(container).getAllByTestId("notice").length).toBeGreaterThan(0));
    expect(await axe(container)).toHaveNoViolations();
  });
});
