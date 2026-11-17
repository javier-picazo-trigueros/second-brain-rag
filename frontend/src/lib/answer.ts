import type { FragmentInfo } from "./api";

/** Una cita de la respuesta, ya resuelta contra los fragmentos que el servidor envió. */
export type CitationRef =
  | {
      kind: "valid";
      label: string;
      path: string | null;
      pages: number[]; // páginas de los fragmentos citados (las pone el sistema, no el modelo)
      number: number | null; // número de la nota en esta respuesta (orden de primera cita)
      hint: boolean; // la cita apunta a una nota relacionada (pista), no a evidencia
    }
  | { kind: "unverified"; label: string };

export interface AnswerMarkdown {
  markdown: string;
  refs: CitationRef[];
}

// Una o varias citas [S3][S4] seguidas, o la marca que pone el servidor a una cita que no estaba
// en el contexto: «[cita no verificada: S9]».
const CITATION = /((?:\[S\d{1,3}\])+)|\[cita no verificada(?::\s*([^\]\n]*))?\]/gu;
const ID = /\[(S\d{1,3})\]/gu;

/** Una nota citada en la respuesta, con el número que lleva su chip. */
export interface CitedSource {
  number: number;
  path: string;
  label: string;
  pages: number[];
  hint: boolean;
}

/** Notas citadas en el texto, numeradas por orden de primera cita, con las páginas citadas. */
export function citedSources(text: string, fragments: FragmentInfo[]): CitedSource[] {
  const byId = new Map(fragments.map((f) => [f.id, f]));
  const out: CitedSource[] = [];
  for (const run of text.matchAll(/(?:\[S\d{1,3}\])+/gu)) {
    for (const match of run[0].matchAll(ID)) {
      const fragment = byId.get(match[1]!);
      if (fragment === undefined) continue;
      let entry = out.find((c) => c.path === fragment.path);
      if (entry === undefined) {
        entry = { number: out.length + 1, path: fragment.path, label: fragment.label, pages: [], hint: fragment.kind === "hint" };
        out.push(entry);
      }
      if (fragment.page !== null && !entry.pages.includes(fragment.page)) {
        entry.pages = [...entry.pages, fragment.page].sort((a, b) => a - b);
      }
    }
  }
  return out;
}

// Entre chips contiguos va un espacio fino real: sin él, «[2][1]» se lee y se copia como «21».
const CHIP_SEPARATOR = " ";

function escapeLinkText(text: string): string {
  return text.replace(/[\\`*_[\]]/g, (c) => `\\${c}`);
}

/** «p. 6» o «p. 6, 7»: lo que se muestra junto al título de la nota. */
export function pagesLabel(pages: number[]): string {
  return pages.length === 0 ? "" : `p. ${pages.join(", ")}`;
}

/** Agrupa fragmentos consecutivos de la misma nota en una sola cita con sus páginas. */
function mergeRun(ids: string[], byId: Map<string, FragmentInfo>): CitationRef[] {
  const refs: CitationRef[] = [];
  for (const id of ids) {
    const fragment = byId.get(id);
    if (fragment === undefined) {
      refs.push({ kind: "valid", label: id, path: null, pages: [], number: null, hint: false });
      continue;
    }
    const last = refs[refs.length - 1];
    if (last?.kind === "valid" && last.path === fragment.path) {
      if (fragment.page !== null && !last.pages.includes(fragment.page)) {
        last.pages = [...last.pages, fragment.page].sort((a, b) => a - b);
      }
      continue;
    }
    refs.push({
      kind: "valid",
      label: fragment.label,
      path: fragment.path,
      pages: fragment.page === null ? [] : [fragment.page],
      number: null,
      hint: fragment.kind === "hint",
    });
  }
  return refs;
}

/**
 * Convierte el texto de la respuesta en Markdown donde cada cita es un enlace `cite:N`; el
 * visor los pinta como chips. Así las citas funcionan dentro de listas, negritas, etc.
 * Las citas seguidas de una misma nota se funden en un solo chip («Nota · p. 6, 7»).
 */
export function answerToMarkdown(text: string, fragments: FragmentInfo[]): AnswerMarkdown {
  const byId = new Map(fragments.map((f) => [f.id, f]));
  const numbers = new Map(citedSources(text, fragments).map((c) => [c.path, c.number]));
  const refs: CitationRef[] = [];
  const link = (ref: CitationRef): string => {
    const index = refs.push(ref) - 1;
    const shown =
      ref.kind === "unverified"
        ? ref.label || "cita no verificada"
        : [ref.label, pagesLabel(ref.pages)].filter(Boolean).join(" · ");
    return `[${escapeLinkText(shown)}](cite:${index})`;
  };
  const markdown = text.replace(CITATION, (_match, run?: string, unverified?: string) => {
    if (run === undefined) return link({ kind: "unverified", label: (unverified ?? "").trim() });
    const ids = [...run.matchAll(ID)].map((m) => m[1]!);
    return mergeRun(ids, byId)
      .map((ref) => link(ref.kind === "valid" && ref.path !== null ? { ...ref, number: numbers.get(ref.path) ?? null } : ref))
      .join(CHIP_SEPARATOR);
  });
  return { markdown, refs };
}
