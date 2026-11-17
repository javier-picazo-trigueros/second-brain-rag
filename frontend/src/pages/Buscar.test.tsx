import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { axe } from "vitest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NoteContext } from "../hooks/notePanel";
import { ApiError, type SearchNote, type SearchResponse } from "../lib/api";
import { Buscar } from "./Buscar";

const apiPost = vi.hoisted(() => vi.fn());
const apiGet = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiPost,
  apiGet,
}));

const note = (over: Partial<SearchNote> = {}): SearchNote => ({
  path: "3º/Discretas/Tema 5 Teoría de grafos.md",
  title: "Tema 5 Teoría de grafos",
  score: 0.5,
  n_chunks: 141,
  asignatura: "Matemática Discreta",
  curso: "3º",
  tags: ["grafos", "matematicas"],
  also_in: [],
  chunks: [
    { heading_path: "Grafos > Definiciones", page: 7, text: "Un grafo dirigido tiene aristas con sentido.", score: 0.5 },
  ],
  ...over,
});

const response = (over: Partial<SearchResponse> = {}): SearchResponse => ({
  notes: [note()],
  top_similarity: 0.6,
  confidence: "alta",
  facets: {
    asignaturas: [
      { value: "Matemática Discreta", count: 3 },
      { value: "Redes", count: 1 },
    ],
    cursos: [{ value: "3º", count: 4 }],
    tags: [{ value: "grafos", count: 3 }],
  },
  ...over,
});

const open = vi.fn();

function Probe() {
  const location = useLocation();
  return <span data-testid="url">{location.search}</span>;
}

function setup(url = "/buscar") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <NoteContext.Provider value={{ open, close: vi.fn() }}>
        <Buscar />
        <Probe />
      </NoteContext.Provider>
    </MemoryRouter>,
  );
}

const lastBody = () => apiPost.mock.calls.at(-1)?.[1] as Record<string, unknown>;

beforeEach(() => {
  apiPost.mockReset();
  apiGet.mockReset();
  open.mockReset();
  apiPost.mockResolvedValue(response());
  apiGet.mockResolvedValue([
    { name: "Redes", notes: 34 },
    { name: "Matemática Discreta", notes: 70 },
  ]);
});

afterEach(() => vi.useRealTimers());

describe("Buscar: estado inicial", () => {
  it("invites to search and offers the subjects as shortcuts, without searching", async () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "Buscar" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Buscar en tus apuntes" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Redes (34)" })).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("filters by a subject shortcut and keeps it in the URL", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Redes (34)" }));
    expect(screen.getByTestId("url")).toHaveTextContent("?asig=Redes");
    expect(screen.getByText(/Escribe algo para buscar en/)).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });
});

describe("Buscar: resultados", () => {
  it("searches what the URL says, without the graph, with up to 20 notes", async () => {
    setup("/buscar?q=grafos&asig=Redes&asig=Data%20Mining&curso=3%C2%BA&tag=ip");
    await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" });
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(apiPost.mock.calls[0]![0]).toBe("/search");
    expect(lastBody()).toEqual({
      query: "grafos",
      k: 20,
      graph: false,
      asignaturas: ["Redes", "Data Mining"],
      cursos: ["3º"],
      tags: ["ip"],
    });
  });

  it("announces how many notes it found", async () => {
    setup("/buscar?q=grafos");
    expect(await screen.findByRole("status")).toHaveTextContent("1 nota");
  });

  it("shows each result with its subject, course, page, tags and a marked snippet", async () => {
    setup("/buscar?q=grafo");
    const card = (await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" })).closest("article")!;
    expect(card).toHaveTextContent("Matemática Discreta");
    expect(card).toHaveTextContent("3º");
    expect(card).toHaveTextContent("p. 7");
    expect(card).toHaveTextContent("grafos");
    expect(card.querySelector("mark")).toHaveTextContent("grafo");
    expect(within(card).getByText("Grafos > Definiciones")).toBeInTheDocument();
  });

  it("opens the note at the page of its best fragment", async () => {
    setup("/buscar?q=grafo");
    await userEvent.click(await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" }));
    expect(open).toHaveBeenCalledWith("3º/Discretas/Tema 5 Teoría de grafos.md", 7);
  });

  it("mentions the other locations of a copied note", async () => {
    apiPost.mockResolvedValue(response({ notes: [note({ also_in: ["1º/DISCRETAS/x.md", "2º/y.md"] })] }));
    setup("/buscar?q=grafo");
    expect(await screen.findByText("También en 2 ubicaciones")).toBeInTheDocument();
  });

  it("says plainly when nothing matches and offers to drop the filters", async () => {
    apiPost.mockResolvedValue(response({ notes: [] }));
    setup("/buscar?q=zzzz&asig=Redes");
    expect(await screen.findByText(/Ninguna nota encaja/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(screen.getByTestId("url")).toHaveTextContent("?q=zzzz");
  });

  it("explains a service failure as the one red alert", async () => {
    apiPost.mockRejectedValue(new ApiError(503, "Ollama no responde: arráncalo con `ollama serve`."));
    setup("/buscar?q=grafos");
    expect(await screen.findByRole("alert")).toHaveTextContent("Ollama no responde");
  });

  it("shows a loading state while it waits", async () => {
    let finish: (value: SearchResponse) => void = () => {};
    apiPost.mockReturnValue(new Promise<SearchResponse>((resolve) => (finish = resolve)));
    setup("/buscar?q=grafos");
    expect(screen.getByRole("status")).toHaveTextContent("Buscando");
    await act(async () => finish(response()));
    expect(await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" })).toBeInTheDocument();
  });

  it("ignores a slow answer to an older query", async () => {
    let slow: (value: SearchResponse) => void = () => {};
    apiPost.mockReturnValueOnce(new Promise<SearchResponse>((resolve) => (slow = resolve)));
    apiPost.mockResolvedValueOnce(response({ notes: [note({ title: "Respuesta nueva", path: "n.md" })] }));
    setup("/buscar?q=viejo");
    const box = screen.getByRole("searchbox", { name: "Buscar en tus apuntes" });
    await userEvent.clear(box);
    await userEvent.type(box, "nuevo{Enter}");
    await screen.findByRole("button", { name: "Respuesta nueva" });
    await act(async () => slow(response({ notes: [note({ title: "Respuesta vieja", path: "v.md" })] })));
    expect(screen.queryByRole("button", { name: "Respuesta vieja" })).toBeNull();
    expect(screen.getByRole("button", { name: "Respuesta nueva" })).toBeInTheDocument();
  });
});

describe("Buscar: escribir y filtrar", () => {
  it("searches at once on Enter and puts the query in the URL", async () => {
    setup();
    await userEvent.type(screen.getByRole("searchbox", { name: "Buscar en tus apuntes" }), "grafos{Enter}");
    expect(screen.getByTestId("url")).toHaveTextContent("?q=grafos");
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1));
  });

  it("searches by itself shortly after the user stops typing, not on every key", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    setup();
    await user.type(screen.getByRole("searchbox", { name: "Buscar en tus apuntes" }), "grafos");
    expect(apiPost).not.toHaveBeenCalled();
    await act(async () => void vi.advanceTimersByTime(400));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1));
    expect(lastBody().query).toBe("grafos");
  });

  it("ticks facets (OR inside, AND across) and searches again with them", async () => {
    setup("/buscar?q=grafos");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Matemática Discreta (3)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Redes (1)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "3º (4)" }));
    await waitFor(() =>
      expect(lastBody()).toMatchObject({ asignaturas: ["Matemática Discreta", "Redes"], cursos: ["3º"], tags: [] }),
    );
    const url = new URLSearchParams(screen.getByTestId("url").textContent ?? "");
    expect(url.getAll("asig")).toEqual(["Matemática Discreta", "Redes"]);
    expect(url.getAll("curso")).toEqual(["3º"]);
  });

  it("clears the query with its button and goes back to the initial state", async () => {
    setup("/buscar?q=grafos");
    await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" });
    await userEvent.click(screen.getByRole("button", { name: "Borrar la búsqueda" }));
    expect(screen.getByTestId("url")).toHaveTextContent("");
    expect(screen.queryByRole("button", { name: "Tema 5 Teoría de grafos" })).toBeNull();
  });

  it("has a filters toggle for small screens that counts the active filters", async () => {
    setup("/buscar?q=grafos&asig=Redes&tag=x");
    const toggle = await screen.findByRole("button", { name: "Filtros (2)" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

describe("Buscar: accesibilidad", () => {
  it("has no violations with results, facets and filters on screen", async () => {
    const { container } = setup("/buscar?q=grafo&asig=Redes");
    await screen.findByRole("button", { name: "Tema 5 Teoría de grafos" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
