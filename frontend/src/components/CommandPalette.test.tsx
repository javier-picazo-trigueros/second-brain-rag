import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type SearchResponse } from "../lib/api";
import { CommandPalette } from "./CommandPalette";

const apiPost = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiPost,
}));

const result = (titles: string[]): SearchResponse => ({
  notes: titles.map((title, i) => ({
    path: `3º/Redes/${title}.md`,
    title,
    score: 1 - i / 10,
    n_chunks: 3,
    asignatura: "Redes",
    curso: "3º",
    tags: [],
    also_in: [],
    chunks: [],
  })),
  top_similarity: 0.7,
  confidence: "alta",
  facets: { asignaturas: [], cursos: [], tags: [] },
});

function Where() {
  const location = useLocation();
  return <span data-testid="where">{decodeURIComponent(location.pathname + location.search)}</span>;
}

function setup(props: Partial<Parameters<typeof CommandPalette>[0]> = {}) {
  const onClose = vi.fn();
  const onNewConversation = vi.fn();
  render(
    <MemoryRouter initialEntries={["/estado"]}>
      <button type="button">antes</button>
      <Routes>
        <Route path="*" element={<CommandPalette open onClose={onClose} onNewConversation={onNewConversation} {...props} />} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
  return { onClose, onNewConversation };
}

beforeEach(() => {
  apiPost.mockReset();
  apiPost.mockResolvedValue(result(["Subnetting", "Routing"]));
});

describe("CommandPalette", () => {
  it("renders nothing while closed", () => {
    render(
      <MemoryRouter>
        <CommandPalette open={false} onClose={() => {}} onNewConversation={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is a modal dialog with the field focused and the quick actions listed", () => {
    setup();
    const dialog = screen.getByRole("dialog", { name: "Buscar o ir a…" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const box = screen.getByRole("combobox", { name: "Buscar en tus apuntes o ir a una pantalla" });
    expect(box).toHaveFocus();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Preguntar",
      "Buscar",
      "Estado",
      "Nueva conversación",
    ]);
  });

  it("goes to a screen with Enter on the highlighted action", async () => {
    const { onClose } = setup();
    await userEvent.keyboard("{ArrowDown}{Enter}"); // 1.ª acción activa por defecto → 2.ª = Buscar
    expect(screen.getByTestId("where")).toHaveTextContent("/buscar");
    expect(onClose).toHaveBeenCalled();
  });

  it("starts a new conversation from the actions", async () => {
    const { onNewConversation, onClose } = setup();
    await userEvent.click(screen.getByRole("option", { name: "Nueva conversación" }));
    expect(onNewConversation).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("searches as you type (without the graph) and lists the notes with their subject", async () => {
    setup();
    await userEvent.type(screen.getByRole("combobox"), "subnetting");
    expect(await screen.findByRole("option", { name: /Subnetting/ })).toHaveTextContent("Redes · 3º");
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    const body = apiPost.mock.calls.at(-1)![1] as { query: string; graph: boolean };
    expect(body).toMatchObject({ query: "subnetting", graph: false });
    expect(screen.queryByRole("option", { name: "Estado" })).toBeNull();
  });

  it("opens the chosen note on its screen", async () => {
    const { onClose } = setup();
    await userEvent.type(screen.getByRole("combobox"), "rutas");
    await userEvent.click(await screen.findByRole("option", { name: /Routing/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/nota/3º/Redes/Routing.md");
    expect(onClose).toHaveBeenCalled();
  });

  it("moves with the arrows, wraps around and keeps aria-activedescendant in sync", async () => {
    setup();
    await userEvent.type(screen.getByRole("combobox"), "x");
    await screen.findByRole("option", { name: /Subnetting/ });
    const box = screen.getByRole("combobox");
    const first = screen.getAllByRole("option")[0]!;
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(box).toHaveAttribute("aria-activedescendant", first.id);
    await userEvent.keyboard("{ArrowUp}");
    const last = screen.getAllByRole("option").at(-1)!;
    expect(last).toHaveAttribute("aria-selected", "true");
    expect(box).toHaveAttribute("aria-activedescendant", last.id);
  });

  it("offers to see all the results in the Buscar screen, with the query", async () => {
    setup();
    await userEvent.type(screen.getByRole("combobox"), "grafos y árboles");
    await screen.findByRole("option", { name: /Subnetting/ });
    await userEvent.click(screen.getByRole("option", { name: /Ver todos los resultados/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/buscar?q=grafos+y+árboles");
  });

  it("says plainly when nothing was found", async () => {
    apiPost.mockResolvedValue(result([]));
    setup();
    await userEvent.type(screen.getByRole("combobox"), "zzz");
    expect(await screen.findByText("Sin resultados para «zzz».")).toBeInTheDocument();
  });

  it("shows a failure as an alert instead of an empty list", async () => {
    apiPost.mockRejectedValue(new ApiError(0, "No se puede conectar con la API."));
    setup();
    await userEvent.type(screen.getByRole("combobox"), "algo");
    expect(await screen.findByRole("alert")).toHaveTextContent("No se puede conectar");
  });

  it("closes with Escape and with a click outside the panel", async () => {
    const { onClose } = setup();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByTestId("palette-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("keeps the focus inside the dialog when Tab is pressed", async () => {
    setup();
    await userEvent.tab();
    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("has no accessibility violations", async () => {
    setup();
    await userEvent.type(screen.getByRole("combobox"), "x");
    await screen.findByRole("option", { name: /Subnetting/ });
    expect(await axe(screen.getByRole("dialog"))).toHaveNoViolations();
  });
});
