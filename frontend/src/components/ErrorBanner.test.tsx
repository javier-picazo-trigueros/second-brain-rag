import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import { ErrorBanner, extractCommand } from "./ErrorBanner";

describe("extractCommand", () => {
  it("finds the command in backticks", () => {
    expect(extractCommand("Ollama no responde en http://x: arráncalo con `ollama serve`.")).toBe("ollama serve");
  });
  it("returns the first one when there are several", () => {
    expect(extractCommand("Usa `a b` o `c`")).toBe("a b");
  });
  it("is null without backticks", () => {
    expect(extractCommand("Algo falló")).toBeNull();
  });
});

describe("ErrorBanner", () => {
  it("is an alert with the message", () => {
    render(<ErrorBanner message="Ollama no responde en http://x: arráncalo con `ollama serve`." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Ollama no responde");
  });

  it("offers to copy the fix command", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<ErrorBanner message="Arráncalo con `ollama serve`." />);
    await userEvent.click(screen.getByRole("button", { name: "Copiar el comando: ollama serve" }));
    expect(writeText).toHaveBeenCalledWith("ollama serve");
    expect(await screen.findByText("Copiado")).toBeInTheDocument();
  });

  it("has no copy button when there is no command", () => {
    render(<ErrorBanner message="Algo falló" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("does not crash if the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    render(<ErrorBanner message="Arráncalo con `ollama serve`." />);
    await userEvent.click(screen.getByRole("button", { name: /Copiar el comando/ }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<ErrorBanner message="Arráncalo con `ollama serve`." />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
