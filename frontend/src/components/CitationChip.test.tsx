import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import type { CitationRef } from "../lib/answer";
import { CitationChip } from "./CitationChip";

const valid = (over: Partial<Extract<CitationRef, { kind: "valid" }>> = {}): CitationRef => ({
  kind: "valid",
  label: "Semáforos",
  path: "1º/SO/Semáforos.md",
  pages: [],
  number: 2,
  hint: false,
  ...over,
});

describe("CitationChip", () => {
  it("is a small numbered button that opens the note", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid()} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: /Semáforos/ });
    expect(button).toHaveTextContent(/^2$/);
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", null);
  });

  it("keeps the title and page out of the text, in a tooltip attribute and the accessible name", async () => {
    const onOpen = vi.fn();
    const { container } = render(
      <p>
        Dato <CitationChip citation={valid({ pages: [7] })} onOpen={onOpen} /> fin.
      </p>,
    );
    const button = screen.getByRole("button", { name: "Abrir «Semáforos», página 7" });
    expect(button).toHaveAttribute("data-tip", "Semáforos · p. 7");
    expect(container.textContent).toBe("Dato 2 fin."); // sin título dentro de la respuesta
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", 7);
  });

  it("lists several pages and opens the first", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid({ pages: [6, 7, 9] })} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "Abrir «Semáforos», páginas 6, 7 y 9" });
    expect(button).toHaveAttribute("data-tip", "Semáforos · p. 6, 7, 9");
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", 6);
  });

  it("activates with the keyboard", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid()} onOpen={onOpen} />);
    await userEvent.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("presents a related-note citation as 'ver también'", () => {
    render(<CitationChip citation={valid({ label: "Redes", hint: true })} onOpen={() => {}} />);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("data-kind", "hint");
    expect(button).toHaveAccessibleName(/Ver también «Redes»/);
  });

  it("is not interactive when the note cannot be opened", () => {
    render(<CitationChip citation={valid({ path: null, number: null })} onOpen={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Semáforos")).toBeInTheDocument();
  });

  it("shows an unverified citation as a calm, focusable «?» (not an error)", () => {
    const { container } = render(
      <p>
        Dato <CitationChip citation={{ kind: "unverified", label: "Inventada" }} onOpen={() => {}} /> fin.
      </p>,
    );
    const note = screen.getByRole("note");
    expect(note).toHaveAccessibleName(/cita no verificada: Inventada/i);
    expect(note).toHaveAccessibleDescription(/no estaba entre las fuentes consultadas/);
    expect(note).toHaveAttribute("tabindex", "0");
    expect(note).toHaveAttribute("data-kind", "unverified");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    // Regresión: la explicación nunca se escribe dentro del texto de la respuesta.
    expect(container.textContent).toBe("Dato ? fin.");
  });

  it("copes with an unverified citation that has no name", () => {
    render(<CitationChip citation={{ kind: "unverified", label: "" }} onOpen={() => {}} />);
    expect(screen.getByRole("note")).toHaveAccessibleName("Cita no verificada");
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <p>
        <CitationChip citation={valid({ pages: [7] })} onOpen={() => {}} />
        <CitationChip citation={valid({ hint: true, label: "Redes", number: 3 })} onOpen={() => {}} />
        <CitationChip citation={{ kind: "unverified", label: "X" }} onOpen={() => {}} />
      </p>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
