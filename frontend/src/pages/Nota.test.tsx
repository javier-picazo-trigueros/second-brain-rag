import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type NoteDetail } from "../lib/api";
import { Nota } from "./Nota";

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiGet,
}));

const note: NoteDetail = {
  path: "3º/Discretas/Tema 5 Teoría de grafos.md",
  title: "Tema 5 Teoría de grafos",
  asignatura: "Matemática Discreta",
  curso: "3º",
  frontmatter: {},
  tags: ["grafos"],
  concepts: ["arbol"],
  links: ["Tema 4", "Intro", "No existe"],
  body: [
    "# Teoría de grafos",
    "",
    "Antes veamos [[Tema 4|el tema anterior]], la [[Intro]] y [[No existe]].",
    "",
    "## Definiciones",
    "",
    "Un grafo es un par.",
    "",
    "## Página 7",
    "",
    "Texto de la página siete.",
    "",
    "### Subapartado",
    "",
    "Más texto.",
  ].join("\n"),
  related: [{ path: "3º/Discretas/Tema 6.md", title: "Tema 6", score: 1, via: ["grafo"] }],
  resolved_links: {
    "Tema 4": ["3º/Discretas/Tema 4.md"],
    Intro: ["3º/DM/Intro.md", "3º/Redes/Intro.md"],
    "No existe": [],
  },
  backlinks: [{ path: "3º/Discretas/Resumen.md", title: "Resumen" }],
  obsidian_url: "obsidian://open?vault=Cerebro&file=3%C2%BA%2FDiscretas%2FTema%205%20Teor%C3%ADa%20de%20grafos",
};

function Where() {
  const location = useLocation();
  return <span data-testid="where">{decodeURIComponent(location.pathname) + location.hash}</span>;
}

function setup(url = "/nota/3%C2%BA/Discretas/Tema%205%20Teor%C3%ADa%20de%20grafos.md") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/nota/*" element={<Nota />} />
        <Route path="/buscar" element={<h1>Buscar</h1>} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiGet.mockReset();
  apiGet.mockResolvedValue(note);
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Nota (pantalla completa)", () => {
  it("loads the note by the path in the URL and shows it as the page heading", async () => {
    setup();
    expect(screen.getByRole("status")).toHaveTextContent("Cargando nota");
    expect(await screen.findByRole("heading", { level: 1, name: "Tema 5 Teoría de grafos" })).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith("/notes/3%C2%BA/Discretas/Tema%205%20Teor%C3%ADa%20de%20grafos.md");
  });

  it("shows the subject, course, tags and concepts", async () => {
    setup();
    expect(await screen.findByText("Matemática Discreta · 3º")).toBeInTheDocument();
    expect(screen.getByText("grafos")).toBeInTheDocument();
    expect(screen.getByText("arbol")).toBeInTheDocument();
  });

  it("opens the note in Obsidian with the link the server built", async () => {
    setup();
    const link = await screen.findByRole("link", { name: "Abrir en Obsidian" });
    expect(link).toHaveAttribute("href", note.obsidian_url);
  });

  it("copies the path of the note", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Copiar la ruta" }));
    expect(writeText).toHaveBeenCalledWith("3º/Discretas/Tema 5 Teoría de grafos.md");
    expect(await screen.findByText("Copiada")).toBeInTheDocument();
  });

  it("has a table of contents with a link to every heading", async () => {
    setup();
    const toc = await screen.findByRole("navigation", { name: "Índice de la nota" });
    const names = within(toc).getAllByRole("link").map((a) => a.textContent);
    expect(names).toEqual(["Teoría de grafos", "Definiciones", "Página 7", "Subapartado"]);
    expect(within(toc).getByRole("link", { name: "Definiciones" })).toHaveAttribute("href", "#definiciones");
  });

  it("scrolls to the cited page", async () => {
    setup("/nota/3%C2%BA/Discretas/Tema%205%20Teor%C3%ADa%20de%20grafos.md?p=7");
    await screen.findByText("Texto de la página siete.");
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    expect(document.getElementById("pagina-7")).not.toBeNull();
  });

  it("scrolls to the heading in the URL hash", async () => {
    setup("/nota/3%C2%BA/Discretas/Tema%205%20Teor%C3%ADa%20de%20grafos.md#definiciones");
    await screen.findByText("Un grafo es un par.");
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
  });

  it("does not scroll when neither page nor heading is asked for", async () => {
    setup();
    await screen.findByText("Un grafo es un par.");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("follows a resolved [[link]] to the other note's screen", async () => {
    setup();
    await userEvent.click(await screen.findByRole("link", { name: "el tema anterior" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/nota/3º/Discretas/Tema 4.md");
  });

  it("asks which note is meant by an ambiguous [[link]]", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Intro" }));
    await userEvent.click(screen.getByRole("button", { name: "3º/Redes/Intro.md" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/nota/3º/Redes/Intro.md");
  });

  it("shows a link to a missing note as non-clickable text", async () => {
    setup();
    expect((await screen.findByText("No existe")).closest("a")).toBeNull();
  });

  it("lists related notes and the notes that link here", async () => {
    setup();
    const related = await screen.findByRole("region", { name: "Relacionadas" });
    await userEvent.click(within(related).getByRole("button", { name: /Tema 6/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/nota/3º/Discretas/Tema 6.md");
  });

  it("lists the backlinks", async () => {
    setup();
    const back = await screen.findByRole("region", { name: "Notas que enlazan aquí" });
    expect(within(back).getByRole("button", { name: /Resumen/ })).toBeInTheDocument();
  });

  it("says plainly that a missing note no longer exists and offers to search", async () => {
    apiGet.mockRejectedValue(new ApiError(404, "La nota no está en el índice."));
    setup("/nota/no/existe.md");
    expect(await screen.findByText("La nota no está en el índice.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Buscar en tus apuntes" }));
    expect(screen.getByRole("heading", { name: "Buscar" })).toBeInTheDocument();
  });

  it("shows a service failure as the red alert", async () => {
    apiGet.mockRejectedValue(new ApiError(0, "No se puede conectar con la API. Ejecuta `brain serve`."));
    setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("No se puede conectar");
  });

  it("has no accessibility violations", async () => {
    const { container } = setup();
    await screen.findByRole("heading", { level: 1, name: "Tema 5 Teoría de grafos" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
