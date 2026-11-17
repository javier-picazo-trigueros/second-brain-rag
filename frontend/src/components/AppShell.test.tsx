import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NoteDetail } from "../lib/api";
import { useNotePanel } from "../hooks/notePanel";
import { AppShell } from "./AppShell";

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiGet,
}));

function OpenButton() {
  const { open } = useNotePanel();
  return (
    <button type="button" onClick={() => open("a/Nota.md", 3)}>
      abrir nota
    </button>
  );
}

function setup(initial = "/") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<><h1>Pantalla Preguntar</h1><OpenButton /></>} />
          <Route path="estado" element={<h1>Pantalla Estado</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const note: NoteDetail = {
  path: "a/Nota.md",
  title: "Nota de prueba",
  asignatura: null,
  curso: null,
  frontmatter: {},
  tags: [],
  concepts: [],
  links: [],
  body: "Contenido",
  related: [],
};

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  apiGet.mockReset();
  apiGet.mockResolvedValue(note);
});

describe("AppShell", () => {
  it("has a main navigation with the two screens and marks the current one", () => {
    setup();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Preguntar" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Estado" })).not.toHaveAttribute("aria-current");
  });

  it("navigates between screens", async () => {
    setup();
    await userEvent.click(screen.getByRole("link", { name: "Estado" }));
    expect(screen.getByRole("heading", { name: "Pantalla Estado" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Estado" })).toHaveAttribute("aria-current", "page");
  });

  it("offers a skip link as the first focusable element", async () => {
    setup();
    await userEvent.tab();
    const skip = screen.getByRole("link", { name: "Saltar al contenido" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#contenido");
    expect(screen.getByRole("main")).toHaveAttribute("id", "contenido");
  });

  it("collapses the navigation, keeps the links accessible and remembers the choice", async () => {
    setup();
    const toggle = screen.getByRole("button", { name: "Contraer navegación" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Expandir navegación" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Estado" })).toBeInTheDocument();
    expect(localStorage.getItem("nav-collapsed")).toBe("1");
  });

  it("starts collapsed when it was left collapsed", () => {
    localStorage.setItem("nav-collapsed", "1");
    setup();
    expect(screen.getByRole("button", { name: "Expandir navegación" })).toBeInTheDocument();
  });

  it("cycles the theme and applies it", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /Tema: sistema/ }));
    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.click(screen.getByRole("button", { name: /Tema: claro/ }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("opens a note in the side panel on request and closes it with Escape", async () => {
    setup();
    expect(screen.queryByRole("complementary", { name: "Nota abierta" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "abrir nota" }));
    expect(await screen.findByRole("heading", { name: "Nota de prueba" })).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith("/notes/a/Nota.md");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Nota abierta" })).toBeNull());
  });

  it("has no accessibility violations", async () => {
    const { container } = setup();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("theme button label", () => {
  it("does not repeat the word «Tema»", () => {
    setup();
    const button = screen.getByRole("button", { name: /Tema: sistema/ });
    expect(button).toHaveTextContent(/^Tema: sistema$/);
    expect(button.getAttribute("aria-label")).not.toMatch(/Tema: Tema/);
  });
});

describe("responsive navigation and new conversation", () => {
  it("opens the navigation from a menu button on small screens", async () => {
    setup();
    const menu = screen.getByRole("button", { name: "Abrir navegación" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    expect(screen.getByRole("button", { name: "Cerrar navegación" })).toHaveAttribute("aria-expanded", "true");
  });

  it("closes the small-screen navigation after choosing a screen", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Abrir navegación" }));
    await userEvent.click(screen.getByRole("link", { name: "Estado" }));
    expect(screen.getByRole("button", { name: "Abrir navegación" })).toHaveAttribute("aria-expanded", "false");
  });

  it("has a «Nueva conversación» button that goes back to Preguntar", async () => {
    setup("/estado");
    await userEvent.click(screen.getByRole("button", { name: "Nueva conversación" }));
    expect(screen.getByRole("heading", { name: "Pantalla Preguntar" })).toBeInTheDocument();
  });

  it("keeps the note panel an overlay below the desktop breakpoint", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "abrir nota" }));
    const panel = (await screen.findByRole("complementary", { name: "Nota abierta" })).parentElement!;
    expect(panel.className).toContain("max-lg:fixed");
  });

  it("has a «Buscar» entry between Preguntar and Estado", () => {
    setup();
    const links = within(screen.getByRole("navigation", { name: "Principal" })).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual(["Preguntar", "Buscar", "Estado"]);
    expect(screen.getByRole("link", { name: "Buscar" })).toHaveAttribute("href", "/buscar");
  });
});
