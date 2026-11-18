import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";

import type { DoneEvent, SourceInfo } from "../lib/api";
import { NoticeBar } from "./NoticeBar";

function done(over: Partial<DoneEvent> = {}): DoneEvent {
  return {
    type: "done",
    answer: "x",
    citations: [],
    invalid: [],
    warnings: [],
    not_found: false,
    confidence: "alta",
    similarity: 0.7,
    timings: { retrieval_ms: 180, first_token_ms: 1900, total_ms: 5600, llm_load_ms: 10, tokens_per_second: 47.4 },
    prompt_tokens: 3659,
    completion_tokens: 165,
    ...over,
  };
}

const source = (label: string, kind: "evidence" | "hint"): SourceInfo => ({
  label,
  path: `${label}.md`,
  title: label,
  kind,
  pages: [],
  asignatura: null,
  curso: null,
  truncated: false,
});
const sources = [source("A", "evidence"), source("B", "evidence"), source("C", "hint")];

describe("NoticeBar", () => {
  it("shows no notices for a clean answer, but keeps the details available", () => {
    render(<NoticeBar done={done()} sources={sources} />);
    expect(screen.queryByTestId("notice")).toBeNull();
    expect(screen.getByRole("button", { name: /Cómo se ha respondido/ })).toBeInTheDocument();
  });

  it("shows each visible notice with its title", () => {
    render(
      <NoticeBar
        done={done({ warnings: ["confianza_baja", "citas_no_verificadas"], invalid: ["A"], confidence: "baja" })}
        sources={sources}
      />,
    );
    const notices = screen.getAllByTestId("notice");
    expect(notices.map((n) => n.textContent)).toEqual([
      expect.stringContaining("1 cita no verificada"),
      expect.stringContaining("Relevancia de las fuentes baja"),
    ]);
  });

  it("is deliberately not alarming: no alert role and no danger tone", () => {
    render(
      <NoticeBar
        done={done({ warnings: ["confianza_baja", "citas_no_verificadas", "sin_citas"], invalid: ["A"] })}
        sources={sources}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    for (const notice of screen.getAllByTestId("notice")) {
      expect(notice.getAttribute("data-tone")).toMatch(/^(neutral|caution)$/);
    }
  });

  it("keeps the trimmed-context notice out of the bar", () => {
    render(<NoticeBar done={done({ warnings: ["contexto_recortado"] })} sources={sources} />);
    expect(screen.queryByTestId("notice")).toBeNull();
  });

  it("expands to explain how the answer was produced", async () => {
    render(<NoticeBar done={done({ warnings: ["contexto_recortado", "confianza_baja"], confidence: "baja" })} sources={sources} />);
    const toggle = screen.getByRole("button", { name: /Cómo se ha respondido/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByRole("region", { name: /Cómo se ha respondido/ });
    expect(within(panel).getByText(/2 notas de evidencia y 1 relacionada/)).toBeInTheDocument();
    expect(within(panel).getByText(/Recuperación/)).toHaveTextContent("180 ms");
    expect(within(panel).getByText(/Primer token/)).toHaveTextContent("1,9 s");
    expect(within(panel).getByText(/Total/)).toHaveTextContent("5,6 s");
    expect(within(panel).getByText(/Velocidad/)).toHaveTextContent("47 tok/s");
    expect(within(panel).getByText(/Tokens/)).toHaveTextContent("3.659");
    expect(within(panel).getByText(/Contexto recortado/)).toBeInTheDocument();
  });

  it("explains each notice in the details", async () => {
    render(<NoticeBar done={done({ warnings: ["respuesta_truncada"] })} sources={sources} />);
    await userEvent.click(screen.getByRole("button", { name: /Cómo se ha respondido/ }));
    expect(screen.getByText(/pregunta más concreta/)).toBeInTheDocument();
  });

  it("can be hidden for the not-found card, which already explains confidence", () => {
    render(
      <NoticeBar done={done({ warnings: ["confianza_baja"], confidence: "baja" })} sources={sources} hide={["confianza_baja"]} />,
    );
    expect(screen.queryByTestId("notice")).toBeNull();
  });

  it("has no accessibility violations (collapsed and expanded)", async () => {
    const { container } = render(
      <NoticeBar done={done({ warnings: ["confianza_baja", "sin_citas"], confidence: "baja" })} sources={sources} />,
    );
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole("button", { name: /Cómo se ha respondido/ }));
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("NoticeBar summary", () => {
  it("shows total time and speed in one quiet line next to the toggle", () => {
    render(<NoticeBar done={done()} sources={sources} />);
    expect(screen.getByTestId("summary")).toHaveTextContent("5,6 s · 47 tok/s");
  });

  it("omits the speed when it is unknown", () => {
    const d = done({ timings: { ...done().timings, tokens_per_second: null } });
    render(<NoticeBar done={d} sources={sources} />);
    expect(screen.getByTestId("summary")).toHaveTextContent(/^5,6 s$/);
  });
});
