import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import type { SourceInfo } from "../lib/api";
import { NotFoundCard, splitNotFound } from "./NotFoundCard";

const sources: SourceInfo[] = [
  {
    label: "Tema 5",
    path: "t5.md",
    title: "Tema 5",
    kind: "evidence",
    pages: [3],
    asignatura: null,
    curso: null,
    truncated: false,
  },
];

describe("splitNotFound", () => {
  it("returns the model's extra text after the fixed sentence", () => {
    expect(splitNotFound("No lo encuentro en el vault. Podrías mirar: [[Tema 5]].")).toBe(
      "Podrías mirar: [[Tema 5]].",
    );
  });
  it("returns an empty string when there is nothing else", () => {
    expect(splitNotFound("No lo encuentro en el vault.")).toBe("");
  });
  it("tolerates surrounding whitespace", () => {
    expect(splitNotFound("  No lo encuentro en el vault.\n\nVer también [[X]]")).toBe("Ver también [[X]]");
  });
});

describe("NotFoundCard", () => {
  const props = {
    answer: "No lo encuentro en el vault. Podrías mirar: [[Tema 5]] (p. 3).",
    sources,
    evidenceCount: 5,
    lowConfidence: true,
    onOpenNote: () => {},
    onRephrase: () => {},
  };

  it("is a calm card, not an error", () => {
    render(<NotFoundCard {...props} />);
    expect(screen.getByRole("heading", { name: "No lo encuentro en tus apuntes" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says how much was searched", () => {
    render(<NotFoundCard {...props} />);
    expect(screen.getByText(/He mirado 5 notas/)).toBeInTheDocument();
  });

  it("explains the low confidence when it applies", () => {
    const { rerender } = render(<NotFoundCard {...props} />);
    expect(screen.getByText(/se parece poco a lo que hay en tus apuntes/)).toBeInTheDocument();
    rerender(<NotFoundCard {...props} lowConfidence={false} />);
    expect(screen.queryByText(/se parece poco/)).toBeNull();
  });

  it("offers the nearby notes as clickable chips", async () => {
    const onOpenNote = vi.fn();
    render(<NotFoundCard {...props} onOpenNote={onOpenNote} />);
    await userEvent.click(screen.getByRole("button", { name: /Tema 5/ }));
    expect(onOpenNote).toHaveBeenCalledWith("t5.md", 3);
  });

  it("omits the suggestions block when the model gave none", () => {
    render(<NotFoundCard {...props} answer="No lo encuentro en el vault." />);
    expect(screen.queryByText(/Notas cercanas/)).toBeNull();
  });

  it("lets the user rephrase", async () => {
    const onRephrase = vi.fn();
    render(<NotFoundCard {...props} onRephrase={onRephrase} />);
    await userEvent.click(screen.getByRole("button", { name: "Reformular la pregunta" }));
    expect(onRephrase).toHaveBeenCalled();
  });

  it("offers a search only when the search screen exists", async () => {
    const onSearch = vi.fn();
    const { rerender } = render(<NotFoundCard {...props} />);
    expect(screen.queryByRole("button", { name: /Buscar/ })).toBeNull();
    rerender(<NotFoundCard {...props} onSearch={onSearch} />);
    await userEvent.click(screen.getByRole("button", { name: /Buscar esto en tus apuntes/ }));
    expect(onSearch).toHaveBeenCalled();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<NotFoundCard {...props} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
