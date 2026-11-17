import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import type { FragmentInfo } from "../lib/api";
import { AnswerView } from "./AnswerView";

const fragments: FragmentInfo[] = [
  {
    id: "S1",
    label: "Semáforos",
    path: "1º/SO/Semáforos.md",
    title: "Semáforos",
    kind: "evidence",
    page: 7,
    heading: null,
  },
];

describe("AnswerView", () => {
  it("renders markdown", () => {
    render(<AnswerView text={"Hay **dos** cosas:\n\n- una\n- otra"} fragments={fragments} onOpenNote={() => {}} />);
    expect(screen.getByText("dos").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("turns citations into chips that open the note at the cited page", async () => {
    const onOpenNote = vi.fn();
    render(<AnswerView text="Cuenta [S1]." fragments={fragments} onOpenNote={onOpenNote} />);
    await userEvent.click(screen.getByRole("button", { name: /Semáforos/ }));
    expect(onOpenNote).toHaveBeenCalledWith("1º/SO/Semáforos.md", 7);
  });

  it("keeps the surrounding text and punctuation", () => {
    const { container } = render(
      <AnswerView text="Antes [S1] después." fragments={fragments} onOpenNote={() => {}} />,
    );
    expect(container).toHaveTextContent(/^Antes Semáforos.*p\. 7 después\.$/);
  });

  it("shows the server's unverified-citation marker as a chip", () => {
    render(
      <AnswerView text="Dato [cita no verificada: Inventada] fin" fragments={fragments} onOpenNote={() => {}} />,
    );
    expect(screen.getByRole("note")).toHaveAccessibleName(/cita no verificada: Inventada/i);
  });

  it("marks itself busy while streaming and not afterwards", () => {
    const { rerender } = render(<AnswerView text="Hola" fragments={fragments} streaming onOpenNote={() => {}} />);
    expect(screen.getByTestId("answer")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("cursor")).toBeInTheDocument();
    rerender(<AnswerView text="Hola" fragments={fragments} onOpenNote={() => {}} />);
    expect(screen.getByTestId("answer")).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByTestId("cursor")).toBeNull();
  });

  it("does not render raw HTML from the model", () => {
    const { container } = render(
      <AnswerView
        text={'<img src=x onerror="alert(1)"> <script>alert(1)</script> <b>negrita</b>'}
        fragments={fragments}
        onOpenNote={() => {}}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("does not create clickable javascript: links", () => {
    const { container } = render(
      <AnswerView text="[pincha](javascript:alert(1))" fragments={fragments} onOpenNote={() => {}} />,
    );
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it("opens ordinary links safely", () => {
    render(<AnswerView text="[web](https://example.org)" fragments={fragments} onOpenNote={() => {}} />);
    const link = screen.getByRole("link", { name: "web" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <AnswerView
        text={"Respuesta con [S1] y [cita no verificada: X].\n\n- punto"}
        fragments={fragments}
        onOpenNote={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
