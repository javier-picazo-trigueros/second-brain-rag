import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

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

describe("SourceCards", () => {
  it("lists the evidence with its context", () => {
    render(<SourceCards sources={sources} onOpen={() => {}} />);
    expect(screen.getByRole("heading", { name: "Fuentes usadas (2)" })).toBeInTheDocument();
    const card = screen.getByRole("button", { name: /Doc iptables/ });
    expect(card).toHaveTextContent("SEGURIDAD");
    expect(card).toHaveTextContent("4º");
    expect(card).toHaveTextContent("p. 4, 21");
  });

  it("keeps the title, the subject and the pages visibly and textually apart", () => {
    // Regresión: salía «Tema-3.1 Procesos e Hilos v2021SISTEMAS».
    render(<SourceCards sources={sources} onOpen={() => {}} />);
    const text = screen.getByRole("button", { name: /Doc iptables/ }).textContent ?? "";
    expect(text).toMatch(/Doc iptables\s+SEGURIDAD/);
    expect(text).not.toMatch(/iptablesSEGURIDAD/);
  });

  it("opens the note at its first page", async () => {
    const onOpen = vi.fn();
    render(<SourceCards sources={sources} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /Doc iptables/ }));
    expect(onOpen).toHaveBeenCalledWith("4º/Seg/Doc iptables.md", 4);
  });

  it("opens a note without pages with no page", async () => {
    const onOpen = vi.fn();
    render(<SourceCards sources={sources} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /Práctica/ }));
    expect(onOpen).toHaveBeenCalledWith("4º/Seg/Práctica.md", null);
  });

  it("says when a source was shortened to fit", () => {
    render(<SourceCards sources={sources} onOpen={() => {}} />);
    expect(screen.getByRole("button", { name: /Práctica/ })).toHaveTextContent("recortada para caber");
  });

  it("keeps the related notes apart, as hints", () => {
    render(<SourceCards sources={sources} onOpen={() => {}} />);
    const hints = screen.getByRole("region", { name: /Notas relacionadas/ });
    expect(within(hints).getByRole("button", { name: /Redes/ })).toBeInTheDocument();
    expect(within(hints).getByText(/pistas/i)).toBeInTheDocument();
  });

  it("renders nothing without sources", () => {
    const { container } = render(<SourceCards sources={[]} onOpen={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<SourceCards sources={sources} onOpen={() => {}} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
