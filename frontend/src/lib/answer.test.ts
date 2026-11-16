import { describe, expect, it } from "vitest";

import type { SourceInfo } from "./api";
import { answerToMarkdown } from "./answer";

function source(label: string, kind: "evidence" | "hint" = "evidence", pages: number[] = []): SourceInfo {
  return {
    label,
    path: `x/${label}.md`,
    title: label,
    kind,
    pages,
    asignatura: null,
    curso: null,
    truncated: false,
  };
}

const SOURCES = [source("Semáforos", "evidence", [7, 9]), source("Redes", "hint")];

describe("answerToMarkdown", () => {
  it("leaves text without citations untouched", () => {
    const result = answerToMarkdown("Un semáforo es un contador.", SOURCES);
    expect(result.markdown).toBe("Un semáforo es un contador.");
    expect(result.refs).toEqual([]);
  });

  it("turns a citation into a link to a reference", () => {
    const { markdown, refs } = answerToMarkdown("Cuenta [[Semáforos]].", SOURCES);
    expect(markdown).toBe("Cuenta [Semáforos](cite:0).");
    expect(refs).toEqual([
      { kind: "valid", label: "Semáforos", path: "x/Semáforos.md", page: null, pageVerified: true, hint: false },
    ]);
  });

  it("absorbs the page into the citation", () => {
    const { markdown, refs } = answerToMarkdown("Cuenta [[Semáforos]] (p. 7).", SOURCES);
    expect(markdown).toBe("Cuenta [Semáforos · p. 7](cite:0).");
    expect(refs[0]).toMatchObject({ page: "7", pageVerified: true });
  });

  it("marks an unverified page", () => {
    const { markdown, refs } = answerToMarkdown("Cuenta [[Semáforos]] (p. 99 no verificada).", SOURCES);
    expect(markdown).toBe("Cuenta [Semáforos · p. 99](cite:0).");
    expect(refs[0]).toMatchObject({ page: "99", pageVerified: false });
  });

  it("understands ranges and lists of pages", () => {
    const { refs } = answerToMarkdown("[[Semáforos]] (p. 7-9) y [[Semáforos]] (pp. 7, 9)", SOURCES);
    expect(refs.map((r) => (r.kind === "valid" ? r.page : null))).toEqual(["7-9", "7, 9"]);
  });

  it("flags citations of related notes as hints", () => {
    const { refs } = answerToMarkdown("Ver también [[Redes]].", SOURCES);
    expect(refs[0]).toMatchObject({ kind: "valid", hint: true });
  });

  it("represents an unverified citation as its own reference", () => {
    const { markdown, refs } = answerToMarkdown("Dato [cita no verificada: Inventada] fin", SOURCES);
    expect(markdown).toBe("Dato [Inventada](cite:0) fin");
    expect(refs).toEqual([{ kind: "unverified", label: "Inventada" }]);
  });

  it("handles an unverified citation without a name", () => {
    const { refs } = answerToMarkdown("Dato [cita no verificada] fin", SOURCES);
    expect(refs).toEqual([{ kind: "unverified", label: "" }]);
  });

  it("keeps a valid citation of an unknown label as a non-clickable reference", () => {
    const { refs } = answerToMarkdown("[[Desconocida]]", SOURCES);
    expect(refs[0]).toMatchObject({ kind: "valid", label: "Desconocida", path: null });
  });

  it("numbers several references in order", () => {
    const { markdown } = answerToMarkdown("[[Semáforos]] y [[Redes]] y [cita no verificada: X]", SOURCES);
    expect(markdown).toBe("[Semáforos](cite:0) y [Redes](cite:1) y [X](cite:2)");
  });

  it("escapes characters that would break a markdown link", () => {
    const { markdown } = answerToMarkdown("[[a*b_c]] [[d\\e]]", [source("a*b_c"), source("d\\e")]);
    expect(markdown).toBe("[a\\*b\\_c](cite:0) [d\\\\e](cite:1)");
  });

  it("works inside markdown lists and emphasis", () => {
    const text = "- **Semáforos POSIX** [[Semáforos]] (p. 9)\n- Otra cosa";
    expect(answerToMarkdown(text, SOURCES).markdown).toBe(
      "- **Semáforos POSIX** [Semáforos · p. 9](cite:0)\n- Otra cosa",
    );
  });

  it("does not touch a page-like text that does not follow a citation", () => {
    expect(answerToMarkdown("Mira la (p. 5) del texto", SOURCES).markdown).toBe("Mira la (p. 5) del texto");
  });
});
