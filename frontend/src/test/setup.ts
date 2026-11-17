import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, expect } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";

expect.extend(axeMatchers);

// KaTeX se importa bajo demanda: con la suite entera en paralelo el primer render tarda más de 1 s.
configure({ asyncUtilTimeout: 6000 });

afterEach(() => {
  cleanup();
});
