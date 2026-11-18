import { describe, expect, it } from "vitest";

import { headingsOf, notePath, parseWikilinks, slugify } from "./wikilinks";

describe("parseWikilinks", () => {
  it("finds a plain link", () => {
    expect(parseWikilinks("ver [[Tema 5]] ya")).toEqual([
      { raw: "[[Tema 5]]", index: 4, target: "Tema 5", heading: null, label: null, embed: false, note: true },
    ]);
  });

  it("separates heading and label", () => {
    const [a, b, c] = parseWikilinks("[[Tema 5#Grafos]] [[Tema 5|el tema]] [[Tema 5#Grafos|aquí]]");
    expect([a!.target, a!.heading, a!.label]).toEqual(["Tema 5", "Grafos", null]);
    expect([b!.target, b!.heading, b!.label]).toEqual(["Tema 5", null, "el tema"]);
    expect([c!.target, c!.heading, c!.label]).toEqual(["Tema 5", "Grafos", "aquí"]);
  });

  it("treats a block reference like a heading-less link to the note", () => {
    const [link] = parseWikilinks("[[Nota^abc123]]");
    expect(link!.target).toBe("Nota");
  });

  it("preserves the folder to disambiguate equal titles", () => {
    expect(parseWikilinks("[[carpeta/sub/Nota]]")[0]!.target).toBe("carpeta/sub/Nota");
  });

  it("recognises embeds and files that are not notes", () => {
    const [embed, image, pdf] = parseWikilinks("![[Otra nota]] [[foto.png]] [[apuntes.pdf]]");
    expect(embed).toMatchObject({ embed: true, note: true, target: "Otra nota" });
    expect(image).toMatchObject({ embed: false, note: false, target: "foto.png" });
    expect(pdf!.note).toBe(false);
  });

  it("trims spaces inside the brackets and ignores broken syntax", () => {
    expect(parseWikilinks("[[  Tema 5  ]]")[0]!.target).toBe("Tema 5");
    expect(parseWikilinks("[[sin cerrar] y [] y [[]]")).toEqual([]);
  });
});

describe("notePath", () => {
  it("encodes every segment but keeps the slashes", () => {
    expect(notePath("3º/Discretas/Tema 5 [MD].md")).toBe("/nota/3%C2%BA/Discretas/Tema%205%20%5BMD%5D.md");
  });
});

describe("slugify", () => {
  it.each([
    ["Definición de grafo", "definicion-de-grafo"],
    ["  Árboles  y  bosques!! ", "arboles-y-bosques"],
    ["Página 7", "pagina-7"],
    ["C++ y C#", "c-y-c"],
  ])("%s -> %s", (text, slug) => {
    expect(slugify(text)).toBe(slug);
  });
});

describe("headingsOf", () => {
  it("lists the headings of a note with their level and slug", () => {
    const md = "# Uno\n\ntexto\n\n## Sub *dos*\n\n### Tres `x`\n";
    expect(headingsOf(md)).toEqual([
      { level: 1, text: "Uno", slug: "uno" },
      { level: 2, text: "Sub dos", slug: "sub-dos" },
      { level: 3, text: "Tres x", slug: "tres-x" },
    ]);
  });

  it("ignores hashes inside code blocks", () => {
    expect(headingsOf("```\n# no\n```\n\n# Sí")).toEqual([{ level: 1, text: "Sí", slug: "si" }]);
  });

  it("gives repeated headings distinct slugs", () => {
    const slugs = headingsOf("## Ejemplo\n\n## Ejemplo\n").map((h) => h.slug);
    expect(slugs).toEqual(["ejemplo", "ejemplo-2"]);
  });

  it("does not take a line of text that merely starts with a hash as a heading", () => {
    expect(headingsOf("#hashtag y más\n#### \n")).toEqual([]);
  });
});
