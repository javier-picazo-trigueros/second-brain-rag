import { render, screen, waitFor } from "@testing-library/react";
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

const TWO_NOTES: FragmentInfo[] = [
  ...fragments,
  { id: "S2", label: "Hilos", path: "1º/SO/Hilos.md", title: "Hilos", kind: "evidence", page: 3, heading: null },
];

describe("AnswerView", () => {
  it("keeps adjacent chips of different notes apart in the text, as in \"6 7\" not \"67\"", () => {
    const { container } = render(<AnswerView text="Dato [S2][S1]." fragments={TWO_NOTES} onOpenNote={() => {}} />);
    const chips = [...container.querySelectorAll(".cite")];
    expect(chips.map((c) => c.textContent)).toEqual(["1", "2"]);
    expect(container.textContent).toContain("1 2");
    expect(container.textContent).not.toMatch(/12/);
  });

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
    expect(container).toHaveTextContent("Antes 1 después.");
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

describe("AnswerView: títulos con corchetes junto a fórmulas", () => {
  const bracketed: FragmentInfo[] = [
    {
      id: "S1",
      label: "Tema 5 Ejemplo de grafos [MD]",
      path: "3º/Discretas/Tema 5 Ejemplo de grafos [MD].md",
      title: "Tema 5 Ejemplo de grafos [MD]",
      kind: "evidence",
      page: 28,
      heading: null,
    },
  ];

  it("keeps the citation chip when the title has [MD] and the answer has a formula", async () => {
    const text = String.raw`La fórmula de Euler es \(V - E + F = 2\) [S1] y en bloque: \[V - E + F = 2\] [S1].`;
    const { container } = render(<AnswerView text={text} fragments={bracketed} onOpenNote={() => {}} />);
    await waitFor(() => expect(container.querySelector(".katex-display")).not.toBeNull());
    expect(container.querySelectorAll(".cite")).toHaveLength(2);
    expect(container.textContent).not.toContain("cite:");
    expect(container.textContent).not.toContain("](");
    expect(container.textContent).not.toMatch(/MDMD/);
  });

  it("keeps the chip with $...$ formulas too, in the same sentence", async () => {
    const { container } = render(
      <AnswerView text="Vale $V-E+F=2$ [S1]." fragments={bracketed} onOpenNote={() => {}} />,
    );
    await waitFor(() => expect(container.querySelector(".katex")).not.toBeNull());
    expect(container.querySelectorAll(".cite")).toHaveLength(1);
    expect(container.textContent).not.toContain("cite:");
  });

  it("works the same without formulas (the title never reaches the text)", () => {
    const { container } = render(<AnswerView text="Dato [S1]." fragments={bracketed} onOpenNote={() => {}} />);
    expect(container.querySelectorAll(".cite")).toHaveLength(1);
    expect(container.textContent).toBe("Dato 1.");
  });
});
