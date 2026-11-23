import { describe, expect, it } from "vitest";

import { codeOf, looksLikeCode } from "./mathCode";

const C = String.raw`\text{char* arguments[] = { "ls", "-l", "/usr/include", 0 }; execv("/bin/ls", arguments);}`;

describe("looksLikeCode", () => {
  it.each([
    [C],
    [String.raw`char* arguments[] = { "ls", "-l", 0 }; execv("/bin/ls", arguments);`],
    ['printf("hola %d\\n", x);'],
    ["#include <stdio.h>\nint main(void) { return 0; }"],
    [String.raw`\text{for (i = 0; i < n; i++) total += a[i];}`],
  ])("treats %s as code", (body) => {
    expect(looksLikeCode(body)).toBe(true);
  });

  it.each([
    [String.raw`\frac{a}{b} = \sum_{i=1}^{n} x_i`],
    [String.raw`E = mc^2`],
    [String.raw`G = (V, E)`],
    [String.raw`\text{Variance} = \frac{\lambda_i}{\sum \lambda}`],
    [String.raw`f(x) = x^2 + 1`],
    [String.raw`\int_0^1 x\,dx`],
    [String.raw`x \in \{1, 2, 3\}`],
  ])("keeps %s as a formula", (body) => {
    expect(looksLikeCode(body)).toBe(false);
  });
});

describe("codeOf", () => {
  it("removes the \\text{...} wrapper the model puts around code", () => {
    expect(codeOf(C)).toBe('char* arguments[] = { "ls", "-l", "/usr/include", 0 }; execv("/bin/ls", arguments);');
  });

  it("leaves plain code as it is", () => {
    expect(codeOf("int x = 1;\n")).toBe("int x = 1;");
  });
});
