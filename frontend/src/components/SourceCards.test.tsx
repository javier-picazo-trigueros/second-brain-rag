import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import type { CitedSource } from "../lib/answer";
import type { SourceInfo } from "../lib/api";
import { SourceCards } from "./SourceCards";

const make = (over: Partial<SourceInfo>): SourceInfo => ({
  label: "Nota",
  path: "x/Nota.md",
  title: "Nota",
  kind: "evidence",
  pages: [],
  asignatura: null,
  curso: null,
  truncated: false,
  ...over,
});

const sources = [
  make({ label: "Doc iptables", path: "4º/Seg/Doc iptables.md", asignatura: "SEGURIDAD", curso: "4º", pages: [4, 21] }),
  make({ label: "Práctica", path: "4º/Seg/Práctica.md", asignatura: "SEGURIDAD", curso: "4º", truncated: true }),
  make({ label: "Redes", path: "3º/Redes.md", kind: "hint" }),
];

const cited: CitedSource[] = [
  { number: 1, path: "4º/Seg/Doc iptables.md", label: "Doc iptables", pages: [4], hint: false },
  { number: 2, path: "3º/Redes.md", label: "Redes", pages: [], hint: true },
];

describe("SourceCards", () => {
  it("shows the cited sources as numbered chips with their title and page, always visible", () => {
    render(<SourceCards sources={sources} cited={cited} onOpen={() => {}} />);
    expect(screen.getByRole("heading", { name: "Fuentes · 2" })).toBeInTheDocument();
    const first = screen.getByRole("button", { name: "1 Doc iptables p. 4" });
    expect(first).toHaveTextContent("1");
    expect(first).toHaveTextContent("Doc iptables");
    expect(first).toHaveTextContent("p. 4");
    expect(screen.getByRole("button", { name: "2 Redes" })).toBeInTheDocument();
  });

  it("names each chip with exactly its visible text (WCAG 2.5.3)", () => {
    render(<SourceCards sources={sources} cited={cited} onOpen={() => {}} />);
    for (const button of screen.getAllByRole("button", { name: /^\d / })) {
      expect(button).not.toHaveAttribute("aria-label");
    }
  });

  it("opens the note at the first cited page, or with none", async () => {
    const onOpen = vi.fn();
    render(<SourceCards sources={sources} cited={cited} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /Doc iptables/ }));
    expect(onOpen).toHaveBeenLastCalledWith("4º/Seg/Doc iptables.md", 4);
    await userEvent.click(screen.getByRole("button", { name: /Redes/ }));
    expect(onOpen).toHaveBeenLastCalledWith("3º/Redes.md", null);
  });

  it("keeps the title and the page visibly and textually apart", () => {
    // Regresión: salía «Tema-3.1 Ejemplo de procesos v2021SISTEMAS».
    render(<SourceCards sources={sources} cited={cited} onOpen={() => {}} />);
    const text = screen.getByRole("button", { name: /Doc iptables/ }).textContent ?? "";
    expect(text).toMatch(/Doc iptables\s+p\. 4/);
  });

  it("hides the consulted-but-not-cited notes until asked, with their subject and course", async () => {
    render(<SourceCards sources={sources} cited={cited} onOpen={() => {}} />);
    expect(screen.queryByText("Práctica")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Ver todas (1 más)" }));
    const other = screen.getByRole("region", { name: "Otras notas consultadas" });
    const card = within(other).getByRole("button", { name: /Práctica/ });
    expect(card).toHaveTextContent("SEGURIDAD");
    expect(card).toHaveTextContent("recortada");
    expect(screen.getByRole("button", { name: "Ver menos" })).toHaveAttribute("aria-expanded", "true");
  });

  it("falls back to the consulted evidence when the answer cited nothing", () => {
    render(<SourceCards sources={sources} cited={[]} onOpen={() => {}} />);
    expect(screen.getByRole("heading", { name: "Fuentes · 2" })).toBeInTheDocument();
    const card = screen.getByRole("button", { name: /Doc iptables/ });
    expect(card).toHaveTextContent("SEGURIDAD");
    expect(within(card).queryByText("1")).toBeNull(); // sin número: nadie la citó
  });

  it("renders nothing without sources", () => {
    const { container } = render(<SourceCards sources={[]} cited={[]} onOpen={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<SourceCards sources={sources} cited={cited} onOpen={() => {}} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
