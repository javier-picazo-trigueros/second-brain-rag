import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import { SaveNote } from "./SaveNote";

const previewGenerated = vi.hoisted(() => vi.fn());
const saveGenerated = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  previewGenerated,
  saveGenerated,
}));

const props = {
  markdown: "# Apuntes del tema 5 de Matemática Discreta\n\n## Parte\n\nContenido $x$ [S1].",
  subject: "Matemática Discreta",
  topic: 5,
  sources: ["3º/Discretas/Tema 5.md", "3º/Discretas/Resumen.md"],
};

beforeEach(() => {
  previewGenerated.mockReset();
  saveGenerated.mockReset();
  previewGenerated.mockResolvedValue({
    path: "_generadas/Apuntes del tema 5 de Matemática Discreta.md",
    content: "---\ntitulo: x\n---\n\nContenido",
  });
  saveGenerated.mockResolvedValue({
    path: "_generadas/Apuntes del tema 5 de Matemática Discreta.md",
    obsidian_url: "obsidian://open?vault=Cerebro&file=_generadas%2FA",
  });
});

describe("SaveNote", () => {
  it("shows a button and writes nothing until it is pressed", () => {
    render(<SaveNote {...props} />);
    expect(screen.getByRole("button", { name: "Guardar como nota" })).toBeInTheDocument();
    expect(previewGenerated).not.toHaveBeenCalled();
    expect(saveGenerated).not.toHaveBeenCalled();
  });

  it("asks for the preview with the title, text, subject, topic and the sources", async () => {
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await screen.findByRole("dialog", { name: "Guardar como nota" });
    expect(previewGenerated.mock.calls[0]![0]).toEqual({
      title: "Apuntes del tema 5 de Matemática Discreta",
      markdown: props.markdown,
      asignatura: "Matemática Discreta",
      tema: 5,
      sources: props.sources,
    });
  });

  it("shows the exact path and content that would be written, and asks for confirmation", async () => {
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    const dialog = await screen.findByRole("dialog", { name: "Guardar como nota" });
    expect(await screen.findByText("_generadas/Apuntes del tema 5 de Matemática Discreta.md")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("titulo: x");
    expect(dialog).toHaveTextContent(/no se sobrescribe/i);
    expect(saveGenerated).not.toHaveBeenCalled(); // enseñar no es escribir
  });

  it("does not offer to save until the preview has loaded", async () => {
    let release: (value: unknown) => void = () => {};
    previewGenerated.mockReturnValue(new Promise((resolve) => (release = resolve)));
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Preparando");
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    release({ path: "_generadas/A.md", content: "c" });
    expect(await screen.findByRole("button", { name: "Guardar" })).toBeEnabled();
  });

  it("writes only after confirming, sending the previewed path and content", async () => {
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await userEvent.click(await screen.findByRole("button", { name: "Guardar" }));
    expect(saveGenerated).toHaveBeenCalledWith({
      path: "_generadas/Apuntes del tema 5 de Matemática Discreta.md",
      content: "---\ntitulo: x\n---\n\nContenido",
    });
  });

  it("reports where it was saved, with a link to open it in Obsidian", async () => {
    saveGenerated.mockResolvedValue({
      path: "_generadas/Apuntes (2).md",
      obsidian_url: "obsidian://open?vault=Cerebro&file=_generadas%2FApuntes%20(2)",
    });
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await userEvent.click(await screen.findByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Guardado en _generadas/Apuntes (2).md");
    expect(screen.getByRole("link", { name: "Abrir en Obsidian" })).toHaveAttribute(
      "href",
      "obsidian://open?vault=Cerebro&file=_generadas%2FApuntes%20(2)",
    );
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull(); // no se guarda dos veces
  });

  it("cancels without writing", async () => {
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await screen.findByRole("button", { name: "Guardar" });
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(saveGenerated).not.toHaveBeenCalled();
  });

  it("closes with Escape and returns the focus to the button", async () => {
    render(<SaveNote {...props} />);
    const button = screen.getByRole("button", { name: "Guardar como nota" });
    await userEvent.click(button);
    await screen.findByRole("button", { name: "Guardar" });
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("shows a failure as an alert and lets the user retry", async () => {
    saveGenerated.mockRejectedValueOnce(new ApiError(400, "Solo se puede guardar un .md en _generadas/."));
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await userEvent.click(await screen.findByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Solo se puede guardar");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(saveGenerated).toHaveBeenCalledTimes(2));
  });

  it("shows a preview failure as an alert", async () => {
    previewGenerated.mockRejectedValue(new ApiError(0, "No se puede conectar con la API."));
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se puede conectar");
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
  });

  it("uses a fallback title when the text has no heading", async () => {
    render(<SaveNote {...props} markdown="Solo texto" />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await screen.findByRole("dialog");
    expect(previewGenerated.mock.calls[0]![0].title).toBe("Apuntes del tema 5 de Matemática Discreta");
  });

  it("has no accessibility violations", async () => {
    render(<SaveNote {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar como nota" }));
    await screen.findByRole("button", { name: "Guardar" });
    expect(await axe(screen.getByRole("dialog"))).toHaveNoViolations();
  });
});
