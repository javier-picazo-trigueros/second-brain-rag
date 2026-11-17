import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type NoteDetail } from "../lib/api";
import { NotePanel } from "./NotePanel";

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  apiGet,
}));

const note: NoteDetail = {
  path: "1º/SO/Semáforos.md",
  title: "Semáforos y monitores",
  asignatura: "SISTEMAS OPERATIVOS",
  curso: "1º",
  frontmatter: {},
  tags: ["concurrencia", "sincronizacion"],
  concepts: ["semaforo"],
  links: [],
  body: "# Semáforos\n\nUn semáforo es un contador.\n\n## Página 7\n\nTexto de la página siete.\n\n```c\nsem_t mutex;\n```",
  related: [{ path: "1º/SO/Carreras.md", title: "Carreras", score: 1.2, via: ["semaforo"] }],
};

beforeEach(() => {
  apiGet.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

describe("NotePanel", () => {
  it("shows a loading state and then the note", async () => {
    apiGet.mockResolvedValue(note);
    render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando nota");
    expect(await screen.findByRole("heading", { name: "Semáforos y monitores", level: 2 })).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith("/notes/1%C2%BA/SO/Sem%C3%A1foros.md");
  });

  it("shows the note's metadata", async () => {
    apiGet.mockResolvedValue(note);
    render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    expect(await screen.findByText("SISTEMAS OPERATIVOS · 1º")).toBeInTheDocument();
    expect(screen.getByText("concurrencia")).toBeInTheDocument();
    expect(screen.getByText("semaforo")).toBeInTheDocument();
  });

  it("renders the markdown body with highlighted code", async () => {
    apiGet.mockResolvedValue(note);
    const { container } = render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByText("Un semáforo es un contador.");
    expect(container.querySelector("pre code")).toHaveTextContent("sem_t mutex;");
  });

  it("scrolls to the cited page", async () => {
    apiGet.mockResolvedValue(note);
    render(<NotePanel path={note.path} page={7} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByText("Texto de la página siete.");
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    expect(document.getElementById("pagina-7")).not.toBeNull();
  });

  it("does not scroll when no page is requested", async () => {
    apiGet.mockResolvedValue(note);
    render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByText("Texto de la página siete.");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("lists related notes and opens them", async () => {
    apiGet.mockResolvedValue(note);
    const onOpenNote = vi.fn();
    render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={onOpenNote} />);
    await userEvent.click(await screen.findByRole("button", { name: /Carreras/ }));
    expect(onOpenNote).toHaveBeenCalledWith("1º/SO/Carreras.md", null);
  });

  it("closes with the button and with Escape", async () => {
    apiGet.mockResolvedValue(note);
    const onClose = vi.fn();
    render(<NotePanel path={note.path} onClose={onClose} onOpenNote={() => {}} />);
    await screen.findByRole("heading", { name: "Semáforos y monitores", level: 2 });
    await userEvent.click(screen.getByRole("button", { name: "Cerrar la nota" }));
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("moves the focus into the panel when it opens", async () => {
    apiGet.mockResolvedValue(note);
    render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar la nota" })).toHaveFocus());
  });

  it("explains an error with the server's message", async () => {
    apiGet.mockRejectedValue(new ApiError(404, "La nota no está en el índice."));
    render(<NotePanel path="no/existe.md" onClose={() => {}} onOpenNote={() => {}} />);
    expect(await screen.findByText("La nota no está en el índice.")).toBeInTheDocument();
  });

  it("reloads when another note is opened", async () => {
    apiGet.mockResolvedValue(note);
    const { rerender } = render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByRole("heading", { name: "Semáforos y monitores", level: 2 });
    apiGet.mockResolvedValue({ ...note, path: "otra.md", title: "Otra nota" });
    rerender(<NotePanel path="otra.md" onClose={() => {}} onOpenNote={() => {}} />);
    expect(await screen.findByRole("heading", { name: "Otra nota", level: 2 })).toBeInTheDocument();
  });

  it("does not execute HTML inside a note", async () => {
    apiGet.mockResolvedValue({ ...note, body: 'Hola <img src=x onerror="alert(1)"> <script>alert(1)</script>' });
    const { container } = render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByRole("heading", { name: "Semáforos y monitores", level: 2 });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("has no accessibility violations", async () => {
    apiGet.mockResolvedValue(note);
    const { container } = render(<NotePanel path={note.path} onClose={() => {}} onOpenNote={() => {}} />);
    await screen.findByRole("heading", { name: "Semáforos y monitores", level: 2 });
    expect(await axe(container)).toHaveNoViolations();
  });
});
