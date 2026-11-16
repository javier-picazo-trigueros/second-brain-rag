import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./lib/api")>()),
  apiGet: vi.fn(() => new Promise(() => {})),
}));

describe("App", () => {
  it("shows Preguntar at the root", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
  });

  it("shows Estado at /estado", () => {
    render(
      <MemoryRouter initialEntries={["/estado"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Estado" })).toBeInTheDocument();
  });

  it("falls back to Preguntar on an unknown path", () => {
    render(
      <MemoryRouter initialEntries={["/nada"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Pregunta a tus apuntes" })).toBeInTheDocument();
  });
});
