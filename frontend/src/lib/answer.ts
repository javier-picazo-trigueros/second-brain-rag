import type { SourceInfo } from "./api";

/** Una cita de la respuesta, ya resuelta contra las fuentes que el servidor envió. */
export type CitationRef =
  | {
      kind: "valid";
      label: string;
      path: string | null;
      page: string | null;
      pageVerified: boolean;
      hint: boolean; // la cita apunta a una nota relacionada (pista), no a evidencia
    }
  | { kind: "unverified"; label: string };

export interface AnswerMarkdown {
  markdown: string;
  refs: CitationRef[];
}

// [[Nota]] con página opcional pegada ("(p. 7)", "(pp. 7, 9)", "(p. 7-9)", "(p. 99 no verificada)")
// o la marca que pone el servidor a una cita que no estaba en el contexto.
const PAGE = String.raw`\s*\(\s*(?:pp?|p[áa]gs?)\.?\s*(\d[\d\s,;–y-]*?)(\s+no verificada)?\s*\)`;
const CITATION = new RegExp(
  String.raw`\[\[([^\[\]\n]{1,200})\]\](?:${PAGE})?|\[cita no verificada(?::\s*([^\]\n]*))?\]`,
  "gu",
);

function escapeLinkText(text: string): string {
  return text.replace(/[\\`*_[\]]/g, (c) => `\\${c}`);
}

/**
 * Convierte el texto de la respuesta en Markdown donde cada cita es un enlace `cite:N`; el
 * visor los pinta como chips. Así las citas funcionan dentro de listas, negritas, etc.
 */
export function answerToMarkdown(text: string, sources: SourceInfo[]): AnswerMarkdown {
  const refs: CitationRef[] = [];
  const markdown = text.replace(
    CITATION,
    (_match, label?: string, pages?: string, unverifiedPage?: string, unverifiedTarget?: string) => {
      const index = refs.length;
      if (label === undefined) {
        const target = (unverifiedTarget ?? "").trim();
        refs.push({ kind: "unverified", label: target });
        return `[${escapeLinkText(target || "cita no verificada")}](cite:${index})`;
      }
      const source = sources.find((s) => s.label === label);
      const page = pages === undefined ? null : pages.trim();
      refs.push({
        kind: "valid",
        label,
        path: source?.path ?? null,
        page,
        pageVerified: unverifiedPage === undefined,
        hint: source?.kind === "hint",
      });
      const shown = page === null ? label : `${label} · p. ${page}`;
      return `[${escapeLinkText(shown)}](cite:${index})`;
    },
  );
  return { markdown, refs };
}
