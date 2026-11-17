import { describe, expect, it } from "vitest";

import { normalizeDelimiters } from "./math";
import { mayHaveMath } from "./mathDetect";

describe("mayHaveMath", () => {
  it.each([
    ["Un texto sin fórmulas", false],
    ["Vale $x$", true],
    [String.raw`Sea \(x\)`, true],
    [String.raw`Sea \[x\]`, true],
  ])("%s", (text, expected) => {
    expect(mayHaveMath(text)).toBe(expected);
  });
});

describe("normalizeDelimiters", () => {
  it("turns \\( \\) into $ $ and \\[ \\] into a display block", () => {
    expect(normalizeDelimiters(String.raw`Sea \( x^2 \) y \[ y=1 \] fin`)).toBe("Sea $x^2$ y \n$$\ny=1\n$$\n fin");
  });

  it("puts a lone single-line $$x$$ on its own block", () => {
    expect(normalizeDelimiters("$$a+b$$")).toBe("$$\na+b\n$$");
    expect(normalizeDelimiters("antes\n\n  $$a+b$$  \n\ndespués")).toBe("antes\n\n$$\na+b\n$$\n\ndespués");
  });

  it("leaves an inline $$x$$ in the middle of a sentence as it is", () => {
    expect(normalizeDelimiters("Vale $$a$$ aquí")).toBe("Vale $$a$$ aquí");
  });

  it("does not touch inline code or fenced code", () => {
    const text = ["En `\\(x\\)` y", "", "```tex", String.raw`\[ a \]`, "$$b$$", "```", "", String.raw`fuera \(c\)`].join("\n");
    const out = normalizeDelimiters(text);
    expect(out).toContain("`\\(x\\)`");
    expect(out).toContain("```tex\n\\[ a \\]\n$$b$$\n```");
    expect(out).toContain("fuera $c$");
  });

  it("leaves text without formulas untouched", () => {
    expect(normalizeDelimiters("Nada que ver\n\n- uno\n- dos")).toBe("Nada que ver\n\n- uno\n- dos");
  });
});
