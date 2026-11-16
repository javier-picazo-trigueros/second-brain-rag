import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("toolchain", () => {
  it("renders", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Segundo cerebro" })).toBeInTheDocument();
  });
});
