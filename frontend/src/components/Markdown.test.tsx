import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

import { Markdown } from "./Markdown";
import { WikiLinkContext, type WikiLinkApi } from "./WikiLink";

function setup(markdown: string, resolved: Record<string, string[]>, open = vi.fn()) {
  const api: WikiLinkApi = { resolved, open };
  const view = render(
    <WikiLinkContext.Provider value={api}>
      <Markdown wikilinks>{markdown}</Markdown>
    </WikiLinkContext.Provider>,
  );
  return { open, ...view };
}

describe("wikilinks in markdown", () => {
  it("turns a resolved [[link]] into a link to the note and opens it in the app", async () => {
    const { open } = setup("Ver [[Tema 5]] ahora.", { "Tema 5": ["3º/D/Tema 5.md"] });
    const link = screen.getByRole("link", { name: "Tema 5" });
    expect(link).toHaveAttribute("href", "/nota/3%C2%BA/D/Tema%205.md");
    await userEvent.click(link);
    expect(open).toHaveBeenCalledWith("3º/D/Tema 5.md", null);
  });

  it("uses the label after the bar and goes to the heading after #", async () => {
    const { open } = setup("[[Tema 5#Grafos simples|el apartado]]", { "Tema 5": ["a/Tema 5.md"] });
    const link = screen.getByRole("link", { name: "el apartado" });
    expect(link.getAttribute("href")).toBe("/nota/a/Tema%205.md#grafos-simples");
    await userEvent.click(link);
    expect(open).toHaveBeenCalledWith("a/Tema 5.md", "grafos-simples");
  });

  it("shows the target and heading when there is no label", () => {
    setup("[[Tema 5#Grafos]]", { "Tema 5": ["a/Tema 5.md"] });
    expect(screen.getByRole("link")).toHaveTextContent("Tema 5 › Grafos");
  });

  it("marks a link to a missing note as such, without making it clickable", () => {
    setup("Ver [[No existe]].", { "No existe": [] });
    const missing = screen.getByText("No existe");
    expect(missing.closest("a")).toBeNull();
    expect(missing).toHaveAttribute("title", "No existe en el vault");
    expect(missing).toHaveAttribute("data-state", "missing");
  });

  it("treats a target the server did not resolve as missing", () => {
    setup("[[Desconocida]]", {});
    expect(screen.getByText("Desconocida")).toHaveAttribute("data-state", "missing");
  });

  it("asks which note is meant when the title is ambiguous", async () => {
    const { open } = setup("[[Intro]]", { Intro: ["3º/DM/Intro.md", "3º/Redes/Intro.md"] });
    const toggle = screen.getByRole("button", { name: "Intro" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const options = screen.getAllByRole("button", { name: /Intro/ }).slice(1);
    expect(options.map((o) => o.textContent)).toEqual(["3º/DM/Intro.md", "3º/Redes/Intro.md"]);
    await userEvent.click(options[1]!);
    expect(open).toHaveBeenCalledWith("3º/Redes/Intro.md", null);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the chooser with Escape", async () => {
    setup("[[Intro]]", { Intro: ["a/Intro.md", "b/Intro.md"] });
    const toggle = screen.getByRole("button", { name: "Intro" });
    await userEvent.click(toggle);
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("leaves links inside code untouched", () => {
    const { container } = setup("En código: `[[Tema 5]]` y\n\n```\n[[Tema 5]]\n```", { "Tema 5": ["a/T.md"] });
    expect(screen.queryByRole("link")).toBeNull();
    expect(container.querySelectorAll("code")).toHaveLength(2);
    expect(container.textContent).toContain("[[Tema 5]]");
  });

  it("shows an embed or a non-note file as plain muted text, never loading it", () => {
    const { container } = setup("![[imagen.png]] y ![[Otra nota]]", { "Otra nota": ["a/O.md"] });
    expect(container.querySelector("img")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(container.textContent).toContain("imagen.png");
  });

  it("does not turn wikilinks into links when the feature is off (answers)", () => {
    render(<Markdown>{"Texto [[Tema 5]] fin"}</Markdown>);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("puts a slug id on headings so [[Nota#Apartado]] can scroll to them", () => {
    const { container } = setup("## Definición de grafo\n\n## Página 7", {});
    expect(container.querySelector("#definicion-de-grafo")).not.toBeNull();
    expect(container.querySelector("#pagina-7")).not.toBeNull(); // el ancla de página sigue funcionando
  });

  it("does not let a hostile link target inject a URL", () => {
    const { container } = setup("[[javascript:alert(1)]] [[x](javascript:alert(1))]]", {});
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it("has no accessibility violations with every kind of link", async () => {
    const { container } = setup("[[A]] [[B]] [[C]]", { A: ["x/A.md"], B: ["x/B.md", "y/B.md"], C: [] });
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("heading levels of a note body", () => {
  const levels = (container: HTMLElement) =>
    [...container.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) => `${h.tagName.toLowerCase()}:${h.textContent}`);

  it("hangs the headings from the page title, keeping the structure and never skipping a level", () => {
    const { container } = render(<Markdown headingBase={2}>{"# A\n\n### B\n\n#### C\n\n## D\n"}</Markdown>);
    expect(levels(container)).toEqual(["h2:A", "h3:B", "h4:C", "h3:D"]);
  });

  it("starts at the base even if the note begins at a deeper level", () => {
    const { container } = render(<Markdown headingBase={2}>{"### Primero\n\n#### Segundo\n"}</Markdown>);
    expect(levels(container)).toEqual(["h2:Primero", "h3:Segundo"]);
  });

  it("never goes past h6", () => {
    const md = "# 1\n\n## 2\n\n### 3\n\n#### 4\n\n##### 5\n\n###### 6\n";
    const { container } = render(<Markdown headingBase={4}>{md}</Markdown>);
    expect(levels(container).at(-1)).toBe("h6:6");
  });

  it("leaves the levels alone when no base is given", () => {
    const { container } = render(<Markdown>{"# A\n\n### B\n"}</Markdown>);
    expect(levels(container)).toEqual(["h1:A", "h3:B"]);
  });
});

describe("math (KaTeX, local)", () => {
  const rendered = (container: HTMLElement) => waitFor(() => expect(container.querySelector(".katex")).not.toBeNull());

  it("renders inline $...$ as KaTeX once the module has loaded", async () => {
    const { container } = render(<Markdown>{"La energía es $E = mc^2$ siempre."}</Markdown>);
    await rendered(container);
    expect(container.querySelector(".katex-display")).toBeNull();
    expect(container.textContent).toContain("siempre.");
  });

  it("renders $$...$$ as display math", async () => {
    const { container } = render(<Markdown>{String.raw`$$\frac{a}{b} = \sum_{i=1}^{n} x_i$$`}</Markdown>);
    await waitFor(() => expect(container.querySelector(".katex-display")).not.toBeNull());
  });

  it("accepts the parenthesis and bracket delimiters that models like to write", async () => {
    const { container } = render(<Markdown latexDelimiters>{String.raw`Sea \(x^2\) y

\[\int_0^1 x\,dx\]
`}</Markdown>);
    await waitFor(() => expect(container.querySelector(".katex-display")).not.toBeNull());
    expect(container.querySelectorAll(".katex").length).toBe(2);
  });

  it("leaves dollars inside code alone", async () => {
    const { container } = render(<Markdown>{"En código `$x$` y\n\n```\n$$y$$\n```\n"}</Markdown>);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toContain("$x$");
    expect(container.textContent).toContain("$$y$$");
  });

  it("does not load or run math for text without formulas", () => {
    const { container } = render(<Markdown>{"Texto **normal** sin fórmulas."}</Markdown>);
    expect(container.querySelector("strong")).not.toBeNull();
    expect(container.querySelector(".katex")).toBeNull();
  });

  it("shows invalid TeX without crashing the page", async () => {
    const { container } = render(<Markdown>{String.raw`Mal: $\frac{1$ y luego texto`}</Markdown>);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.textContent).toContain("luego texto");
  });

  it("never turns TeX into a link, script or remote resource (trust off)", async () => {
    const evil = String.raw`$\href{javascript:alert(1)}{click}$ $\url{https://x.test}$ $\includegraphics{https://x.test/a.png}$ $\htmlClass{big}{y}$`;
    const { container } = render(<Markdown>{evil}</Markdown>);
    await new Promise((r) => setTimeout(r, 100));
    expect(container.querySelector("a[href^='javascript']")).toBeNull();
    expect(container.querySelector("a[href^='http']")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".big")).toBeNull();
  });

  it("keeps a [[wikilink]] working next to a formula", async () => {
    const api: WikiLinkApi = { resolved: { Tema: ["a/Tema.md"] }, open: vi.fn() };
    const { container } = render(
      <WikiLinkContext.Provider value={api}>
        <Markdown wikilinks>{"Ver [[Tema]] con $a+b$."}</Markdown>
      </WikiLinkContext.Provider>,
    );
    await rendered(container);
    expect(screen.getByRole("link", { name: "Tema" })).toBeInTheDocument();
  });

  it("has no accessibility violations with a formula", async () => {
    const { container } = render(<Markdown>{String.raw`Dato $x^2$ y

$$y=\frac{1}{2}$$`}</Markdown>);
    await rendered(container);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("math in notes vs answers", () => {
  it("shows an escaped [MD] in a note as plain brackets, next to a $...$ formula", async () => {
    const { container } = render(<Markdown wikilinks>{String.raw`Resumen \[MD\] de la clase con $a+b$ y \(x\).`}</Markdown>);
    await waitFor(() => expect(container.querySelector(".katex")).not.toBeNull());
    expect(container.querySelectorAll(".katex")).toHaveLength(1); // solo $a+b$
    expect(container.textContent).toContain("[MD]");
    expect(container.textContent).toContain("(x)");
    expect(container.querySelector(".katex-display")).toBeNull();
  });
});

describe("code is never rendered as a formula", () => {
  const CODE = String.raw`char* arguments[] = { "ls", "-l", "/usr/include", 0 }; execv("/bin/ls", arguments);`;

  it("shows code the model wrapped in \\[ \\text{...} \\] as a code block, braces and all", async () => {
    const md = String.raw`Ejemplo:

\[ \text{${CODE}} \]

Fin.`;
    const { container } = render(<Markdown latexDelimiters>{md}</Markdown>);
    await waitFor(() => expect(container.querySelector("pre code")).not.toBeNull());
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.querySelector("pre code")!.textContent).toContain('{ "ls", "-l", "/usr/include", 0 }');
    expect(container.textContent).toContain("Fin.");
  });

  it("does the same with $$...$$ blocks and with inline $...$", async () => {
    const md = `$$\n${CODE}\n$$\n\nY en línea: $printf("hola");$ fin.`;
    const { container } = render(<Markdown>{md}</Markdown>);
    await waitFor(() => expect(container.querySelector("pre code")).not.toBeNull());
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.querySelector("pre code")!.textContent).toContain("execv(");
    expect(container.querySelector("code:not(pre code)")!.textContent).toBe('printf("hola");');
  });

  it("keeps a fenced C block with braces exactly as written, once", async () => {
    const md = "```c\nint main(void) {\n  char* a[] = { \"ls\", 0 };\n  return 0;\n}\n```";
    const { container } = render(<Markdown>{md}</Markdown>);
    const code = container.querySelector("pre code")!;
    expect(code.textContent).toContain('char* a[] = { "ls", 0 };');
    expect(container.querySelectorAll("pre")).toHaveLength(1);
    expect(container.querySelector(".katex")).toBeNull();
  });

  it("still renders a real formula next to the code", async () => {
    const md = String.raw`\[ \text{${CODE}} \]

Y la fórmula \(E = mc^2\).`;
    const { container } = render(<Markdown latexDelimiters>{md}</Markdown>);
    await waitFor(() => expect(container.querySelectorAll(".katex")).toHaveLength(1));
    expect(container.querySelector("pre code")).not.toBeNull();
  });
});

describe("code blocks", () => {
  it("can be focused with the keyboard so a long line can be scrolled", () => {
    const { container } = render(<Markdown>{"```c\nint main(void) { return 0; }\n```"}</Markdown>);
    expect(container.querySelector("pre")).toHaveAttribute("tabindex", "0");
  });
});
