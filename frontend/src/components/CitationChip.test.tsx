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
  page: null,
  pageVerified: true,
  hint: false,
  ...over,
});

describe("CitationChip", () => {
  it("is a button that opens the note", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid()} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: /Semáforos/ }));
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", null);
  });

  it("shows the page and passes it on", async () => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid({ page: "7" })} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "Abrir «Semáforos», página 7" });
    expect(button).toHaveTextContent("p. 7");
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", 7);
  });

  it.each([
    ["7-9", 7],
    ["7, 9", 7],
    ["7 y 9", 7],
  ])("opens the first page of %s", async (page, first) => {
    const onOpen = vi.fn();
    render(<CitationChip citation={valid({ page })} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledWith("1º/SO/Semáforos.md", first);
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

  it("flags an unverified page without hiding the citation", () => {
    render(<CitationChip citation={valid({ page: "99", pageVerified: false })} onOpen={() => {}} />);
    const button = screen.getByRole("button");
    expect(button).toHaveAccessibleName(/página 99 no verificada/);
    expect(button).toHaveTextContent("p. 99");
    expect(button).toHaveAttribute("data-page-verified", "false");
  });

  it("presents a related-note citation as 'ver también'", () => {
    render(<CitationChip citation={valid({ label: "Redes", hint: true })} onOpen={() => {}} />);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("data-kind", "hint");
    expect(button).toHaveAccessibleName(/Ver también «Redes»/);
  });

  it("is not interactive when the note cannot be opened", () => {
    render(<CitationChip citation={valid({ path: null })} onOpen={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Semáforos")).toBeInTheDocument();
  });

  it("shows an unverified citation as a calm, focusable note (not an error)", () => {
    render(<CitationChip citation={{ kind: "unverified", label: "Inventada" }} onOpen={() => {}} />);
    const note = screen.getByRole("note");
    expect(note).toHaveAccessibleName(/cita no verificada: Inventada/i);
    expect(note).toHaveAccessibleDescription(/no estaba entre las fuentes consultadas/);
    expect(note).toHaveAttribute("tabindex", "0");
    expect(note).toHaveAttribute("data-kind", "unverified");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("copes with an unverified citation that has no name", () => {
    render(<CitationChip citation={{ kind: "unverified", label: "" }} onOpen={() => {}} />);
    expect(screen.getByRole("note")).toHaveAccessibleName(/cita no verificada/i);
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <p>
        <CitationChip citation={valid({ page: "7" })} onOpen={() => {}} />
        <CitationChip citation={valid({ page: "9", pageVerified: false })} onOpen={() => {}} />
        <CitationChip citation={valid({ label: "Redes", hint: true })} onOpen={() => {}} />
        <CitationChip citation={{ kind: "unverified", label: "X" }} onOpen={() => {}} />
      </p>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
