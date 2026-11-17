import { describe, expect, it } from "vitest";

import type { FragmentInfo } from "./api";
import { answerToMarkdown, pagesLabel } from "./answer";

function fragment(
  id: string,
  label: string,
  page: number | null,
  kind: "evidence" | "hint" = "evidence",
): FragmentInfo {
  return { id, label, path: `x/${label}.md`, title: label, kind, page, heading: null };
}

const FRAGMENTS = [
  fragment("S1", "Semáforos", 7),
  fragment("S2", "Semáforos", 9),
  fragment("S3", "Hilos", null),
  fragment("S4", "Redes", null, "hint"),
  fragment("S5", "Semáforos", 7),
];

describe("pagesLabel", () => {
  it("formats none, one and several pages", () => {
    expect(pagesLabel([])).toBe("");
    expect(pagesLabel([6])).toBe("p. 6");
    expect(pagesLabel([6, 7])).toBe("p. 6, 7");
  });
});

describe("answerToMarkdown", () => {
  it("leaves text without citations untouched", () => {
    const result = answerToMarkdown("Un semáforo es un contador.", FRAGMENTS);
    expect(result.markdown).toBe("Un semáforo es un contador.");
    expect(result.refs).toEqual([]);
  });

  it("turns a citation into a link carrying the page of its fragment", () => {
    const { markdown, refs } = answerToMarkdown("Cuenta [S1].", FRAGMENTS);
    expect(markdown).toBe("Cuenta [Semáforos · p. 7](cite:0).");
    expect(refs).toEqual([
      { kind: "valid", label: "Semáforos", path: "x/Semáforos.md", pages: [7], hint: false },
    ]);
  });

  it("shows a citation without a page as just the title", () => {
    expect(answerToMarkdown("Dato [S3]", FRAGMENTS).markdown).toBe("Dato [Hilos](cite:0)");
  });

  it("merges consecutive citations of the same note into one chip with all its pages", () => {
    const { markdown, refs } = answerToMarkdown("Dato [S2][S1].", FRAGMENTS);
    expect(markdown).toBe("Dato [Semáforos · p. 7, 9](cite:0).");
    expect(refs).toHaveLength(1);
    expect(refs[0]).toMatchObject({ pages: [7, 9] });
  });

  it("does not repeat a page when two fragments share it", () => {
    const { refs } = answerToMarkdown("[S1][S5]", FRAGMENTS);
    expect(refs[0]).toMatchObject({ pages: [7] });
  });

  it("keeps chips of different notes separate, in order", () => {
    const { markdown, refs } = answerToMarkdown("[S1][S3][S2]", FRAGMENTS);
    expect(markdown).toBe("[Semáforos · p. 7](cite:0)[Hilos](cite:1)[Semáforos · p. 9](cite:2)");
    expect(refs.map((r) => (r.kind === "valid" ? r.label : r.kind))).toEqual(["Semáforos", "Hilos", "Semáforos"]);
  });

  it("does not merge citations separated by text", () => {
    const { refs } = answerToMarkdown("[S1] y luego [S2]", FRAGMENTS);
    expect(refs).toHaveLength(2);
  });

  it("flags citations of related notes as hints", () => {
    const { refs } = answerToMarkdown("Ver también [S4].", FRAGMENTS);
    expect(refs[0]).toMatchObject({ kind: "valid", hint: true });
  });

  it("represents an unverified citation as its own reference", () => {
    const { markdown, refs } = answerToMarkdown("Dato [cita no verificada: S9] fin", FRAGMENTS);
    expect(markdown).toBe("Dato [S9](cite:0) fin");
    expect(refs).toEqual([{ kind: "unverified", label: "S9" }]);
  });

  it("handles an unverified citation without a name", () => {
    const { refs } = answerToMarkdown("Dato [cita no verificada] fin", FRAGMENTS);
    expect(refs).toEqual([{ kind: "unverified", label: "" }]);
  });

  it("keeps an id with no fragment as a non-clickable reference", () => {
    const { refs } = answerToMarkdown("[S42]", FRAGMENTS);
    expect(refs[0]).toMatchObject({ kind: "valid", label: "S42", path: null });
  });

  it("escapes characters that would break a markdown link", () => {
    const tricky = [fragment("S1", "a*b_c [MD]", null)];
    expect(answerToMarkdown("[S1]", tricky).markdown).toBe("[a\\*b\\_c \\[MD\\]](cite:0)");
  });

  it("works inside markdown lists and emphasis", () => {
    const text = "- **Semáforos POSIX** [S2]\n- Otra cosa";
    expect(answerToMarkdown(text, FRAGMENTS).markdown).toBe(
      "- **Semáforos POSIX** [Semáforos · p. 9](cite:0)\n- Otra cosa",
    );
  });

  it("does not touch bracketed text that is not a citation", () => {
    expect(answerToMarkdown("array[0] y [nota] y [1]", FRAGMENTS).markdown).toBe("array[0] y [nota] y [1]");
  });
});
