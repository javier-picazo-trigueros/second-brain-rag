import { describe, expect, it } from "vitest";

import {
  EMPTY_FILTERS,
  filtersActive,
  filtersFromParams,
  highlight,
  paramsFromState,
  plainSnippet,
  toggleValue,
} from "./search";

describe("highlight", () => {
  it("splits the text into plain and marked segments", () => {
    expect(highlight("Un semáforo es un contador", "semáforo")).toEqual([
      { text: "Un ", hit: false },
      { text: "semáforo", hit: true },
      { text: " es un contador", hit: false },
    ]);
  });

  it("ignores case and accents but keeps the original text", () => {
    const parts = highlight("El SEMÁFORO y el semaforo", "semáforo");
    expect(parts.filter((p) => p.hit).map((p) => p.text)).toEqual(["SEMÁFORO", "semaforo"]);
  });

  it("marks every word of the query, not the phrase", () => {
    const parts = highlight("grafos dirigidos y no dirigidos", "grafos dirigidos");
    expect(parts.filter((p) => p.hit).map((p) => p.text)).toEqual(["grafos", "dirigidos", "dirigidos"]);
  });

  it("skips very short words (they would mark everything)", () => {
    expect(highlight("de la casa", "de la").every((p) => !p.hit)).toBe(true);
  });

  it("treats the query as plain text, never as a pattern", () => {
    expect(() => highlight("a (b) c.* d", "(b) .* [x")).not.toThrow();
    expect(highlight("hola.*mundo", ".*").every((p) => !p.hit)).toBe(true);
  });

  it("returns the whole text unmarked for an empty query", () => {
    expect(highlight("texto", "  ")).toEqual([{ text: "texto", hit: false }]);
    expect(highlight("", "algo")).toEqual([]);
  });

  it("does not split an accented letter into pieces", () => {
    const parts = highlight("niño canción", "cancion");
    expect(parts.map((p) => p.text).join("")).toBe("niño canción");
    expect(parts.find((p) => p.hit)?.text).toBe("canción");
  });
});

describe("filters in the URL", () => {
  it("reads repeated parameters", () => {
    const params = new URLSearchParams("q=grafos&asig=Redes&asig=Data%20Mining&curso=3º&tag=ip");
    expect(filtersFromParams(params)).toEqual({
      asignaturas: ["Redes", "Data Mining"],
      cursos: ["3º"],
      tags: ["ip"],
    });
  });

  it("reads nothing when there are no filters", () => {
    expect(filtersFromParams(new URLSearchParams("q=x"))).toEqual(EMPTY_FILTERS);
  });

  it("writes the query and the filters back, leaving out what is empty", () => {
    const params = paramsFromState("grafos", { asignaturas: ["Redes"], cursos: [], tags: ["a b", "c"] });
    expect(params.toString()).toBe("q=grafos&asig=Redes&tag=a+b&tag=c");
    expect(paramsFromState("", EMPTY_FILTERS).toString()).toBe("");
  });

  it("round-trips accents, spaces and symbols", () => {
    const filters = { asignaturas: ["Matemática Discreta"], cursos: ["3º"], tags: ["c++ & más"] };
    const params = paramsFromState("¿qué es?", filters);
    const back = new URLSearchParams(params.toString());
    expect(back.get("q")).toBe("¿qué es?");
    expect(filtersFromParams(back)).toEqual(filters);
  });
});

describe("toggleValue and filtersActive", () => {
  it("adds and removes a value", () => {
    expect(toggleValue(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleValue(["a", "b"], "a")).toEqual(["b"]);
  });

  it("knows when any filter is on", () => {
    expect(filtersActive(EMPTY_FILTERS)).toBe(false);
    expect(filtersActive({ ...EMPTY_FILTERS, tags: ["x"] })).toBe(true);
  });
});

describe("plainSnippet", () => {
  it("drops emphasis, headings, quotes and code marks but keeps the words", () => {
    expect(plainSnippet("**Table of sources** **1.** # Título\n> cita `código`")).toBe("Table of sources 1. Título cita código");
  });

  it("keeps the text of links and the label of wikilinks, and drops embeds", () => {
    expect(plainSnippet("ver [la guía](http://x.org) y [[Tema 5|grafos]] o [[Otra#Apartado]] ![[imagen.png]] fin")).toBe(
      "ver la guía y grafos o Otra fin",
    );
    expect(plainSnippet("![foto](a.png) texto")).toBe("texto");
  });

  it("does not eat underscores inside words", () => {
    expect(plainSnippet("mi_variable_larga y __negrita__")).toBe("mi_variable_larga y negrita");
  });

  it("turns list bullets and table pipes into plain spacing", () => {
    expect(plainSnippet("- uno\n- dos\n| a | b |")).toBe("uno dos a b");
  });

  it("collapses whitespace and handles empty text", () => {
    expect(plainSnippet("  a \n\n  b\t c ")).toBe("a b c");
    expect(plainSnippet("")).toBe("");
  });
});
