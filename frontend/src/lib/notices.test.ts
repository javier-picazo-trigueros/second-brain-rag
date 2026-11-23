import { describe, expect, it } from "vitest";

import type { DoneEvent } from "./api";
import { describeNotices, summarizeNotices } from "./notices";

function done(overrides: Partial<DoneEvent> = {}): DoneEvent {
  return {
    type: "done",
    answer: "x",
    citations: [],
    invalid: [],
    warnings: [],
    not_found: false,
    confidence: "alta",
    similarity: 0.7,
    timings: { retrieval_ms: 1, first_token_ms: 1, total_ms: 2, llm_load_ms: 0, tokens_per_second: 40 },
    prompt_tokens: 10,
    completion_tokens: 2,
    ...overrides,
  };
}

describe("describeNotices", () => {
  it("is empty for a clean answer", () => {
    expect(describeNotices(done())).toEqual([]);
  });

  it("explains low confidence with the real numbers and without alarm", () => {
    const [notice] = describeNotices(
      done({ warnings: ["confianza_baja"], confidence: "baja", similarity: 0.566 }),
    );
    expect(notice).toMatchObject({ code: "confianza_baja", tone: "neutral" });
    expect(notice!.title).toBe("Relevancia de las fuentes baja");
    expect(notice!.detail).toContain("0,57");
  });

  it("counts unverified citations with the right plural", () => {
    const one = describeNotices(done({ warnings: ["citas_no_verificadas"], invalid: ["A"] }));
    const two = describeNotices(done({ warnings: ["citas_no_verificadas"], invalid: ["A", "B"] }));
    expect(one[0]!.title).toBe("1 cita no verificada");
    expect(two[0]!.title).toBe("2 citas no verificadas");
    expect(one[0]!.tone).toBe("caution");
  });

  it.each([
    ["sin_citas", "Respuesta sin citas"],
    ["solo_pistas", "Solo cita notas relacionadas"],
    ["respuesta_truncada", "Respuesta cortada"],
    ["parte_sin_terminar", "Apuntes con una parte sin terminar"],
  ])("describes %s", (code, title) => {
    const [notice] = describeNotices(done({ warnings: [code] }));
    expect(notice).toMatchObject({ code, title, tone: "caution" });
  });

  it("tells the user what to do when the answer was cut", () => {
    const [notice] = describeNotices(done({ warnings: ["respuesta_truncada"] }));
    expect(notice!.detail).toMatch(/pregunta más concreta/);
  });

  it("tells the user to ask again for an unfinished part of the notes", () => {
    const [notice] = describeNotices(done({ warnings: ["parte_sin_terminar"] }));
    expect(notice!.detail).toMatch(/volver a pedir/);
  });

  it("keeps the trimmed-context notice out of the summary (it is almost always present)", () => {
    const notices = describeNotices(done({ warnings: ["contexto_recortado"] }));
    expect(notices[0]).toMatchObject({ code: "contexto_recortado", detailsOnly: true });
    expect(summarizeNotices(notices)).toBe("");
  });

  it("orders the notices by importance", () => {
    const codes = describeNotices(
      done({
        warnings: ["confianza_baja", "contexto_recortado", "sin_citas", "citas_no_verificadas"],
        invalid: ["A"],
        confidence: "baja",
      }),
    ).map((n) => n.code);
    expect(codes).toEqual(["citas_no_verificadas", "sin_citas", "confianza_baja", "contexto_recortado"]);
  });

  it("ignores warning codes it does not know", () => {
    expect(describeNotices(done({ warnings: ["algo_nuevo"] }))).toEqual([]);
  });
});

describe("summarizeNotices", () => {
  it("joins the visible titles on one line", () => {
    const notices = describeNotices(
      done({
        warnings: ["citas_no_verificadas", "confianza_baja", "contexto_recortado"],
        invalid: ["A"],
        confidence: "baja",
        similarity: 0.5,
      }),
    );
    expect(summarizeNotices(notices)).toBe("1 cita no verificada · Relevancia de las fuentes baja");
  });
});

describe("respuesta_contradictoria", () => {
  it("explains that what the model wrote was discarded", () => {
    const [notice] = describeNotices(done({ warnings: ["respuesta_contradictoria"] }));
    expect(notice).toMatchObject({ code: "respuesta_contradictoria", tone: "caution" });
    expect(notice!.title).toBe("Respuesta descartada");
    expect(notice!.detail).toContain("no lo encuentra");
  });

  it("goes first, before the other warnings", () => {
    const codes = describeNotices(done({ warnings: ["confianza_baja", "respuesta_contradictoria"] })).map(
      (n) => n.code,
    );
    expect(codes[0]).toBe("respuesta_contradictoria");
  });
});

describe("exercise answers: numbers, steps and partial answers", () => {
  it("lists the numbers that are not in the sources and says to check them", () => {
    const [notice] = describeNotices(
      done({ warnings: ["numeros_no_verificados"], unverified_numbers: ["0,79209", "12,5"] }),
    );
    expect(notice).toMatchObject({ code: "numeros_no_verificados", tone: "caution" });
    expect(notice!.title).toBe("2 números sin verificar");
    expect(notice!.detail).toContain("0,79209");
    expect(notice!.detail).toContain("12,5");
  });

  it("uses the singular for one number", () => {
    const [notice] = describeNotices(done({ warnings: ["numeros_no_verificados"], unverified_numbers: ["7,5"] }));
    expect(notice!.title).toBe("1 número sin verificar");
  });

  it("counts the steps without a citation", () => {
    const [notice] = describeNotices(done({ warnings: ["pasos_sin_cita"], uncited_steps: 3 }));
    expect(notice).toMatchObject({ code: "pasos_sin_cita", tone: "caution" });
    expect(notice!.title).toBe("3 pasos sin cita");
    const [one] = describeNotices(done({ warnings: ["pasos_sin_cita"], uncited_steps: 1 }));
    expect(one!.title).toBe("1 paso sin cita");
  });

  it("explains a partial answer", () => {
    const [notice] = describeNotices(done({ warnings: ["respuesta_parcial"] }));
    expect(notice).toMatchObject({ code: "respuesta_parcial", tone: "caution", title: "Respuesta parcial" });
    expect(notice!.detail).toContain("frases con cita");
  });
});
