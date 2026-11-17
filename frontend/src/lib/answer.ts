import type { FragmentInfo } from "./api";

/** Una cita de la respuesta, ya resuelta contra los fragmentos que el servidor envió. */
export type CitationRef =
  | {
      kind: "valid";
      label: string;
      path: string | null;
      pages: number[]; // páginas de los fragmentos citados (las pone el sistema, no el modelo)
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
      refs.push({ kind: "valid", label: id, path: null, pages: [], hint: false });
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
    return mergeRun(ids, byId).map(link).join("");
  });
  return { markdown, refs };
}
