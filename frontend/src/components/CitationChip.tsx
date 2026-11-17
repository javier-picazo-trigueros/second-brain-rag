import { pagesLabel, type CitationRef } from "../lib/answer";

interface Props {
  citation: CitationRef;
  onOpen: (path: string, page: number | null) => void;
}

const UNVERIFIED_HELP =
  "Esta nota no estaba entre las fuentes consultadas; el modelo la nombró por su cuenta.";

function pagesName(pages: number[]): string {
  if (pages.length === 0) return "";
  if (pages.length === 1) return `, página ${pages[0]}`;
  return `, páginas ${pages.slice(0, -1).join(", ")} y ${pages[pages.length - 1]}`;
}

/**
 * Cita numerada, discreta. El título y la página salen como tooltip (CSS sobre `data-tip`, nunca
 * como texto del párrafo) al pasar el ratón o enfocar; al tocarla se abre la nota.
 */
export function CitationChip({ citation, onOpen }: Props) {
  if (citation.kind === "unverified") {
    const name = citation.label ? `Cita no verificada: ${citation.label}` : "Cita no verificada";
    return (
      <span
        role="note"
        tabIndex={0}
        data-kind="unverified"
        aria-label={name}
        title={UNVERIFIED_HELP}
        className="cite cite-warn"
      >
        ?
      </span>
    );
  }

  const hint = citation.hint;
  const kind = hint ? "hint" : "evidence";
  const pages = pagesLabel(citation.pages);
  const tip = [citation.label, pages].filter(Boolean).join(" · ");
  const shown = citation.number === null ? citation.label : String(citation.number);

  if (citation.path === null) {
    return (
      <span data-kind={kind} className="cite">
        {shown}
      </span>
    );
  }

  const target = citation.path;
  const verb = hint ? `Ver también «${citation.label}»` : `Abrir «${citation.label}»`;
  return (
    <button
      type="button"
      data-kind={kind}
      data-tip={tip}
      aria-label={`${verb}${pagesName(citation.pages)}`}
      onClick={() => onOpen(target, citation.pages[0] ?? null)}
      className={`cite ${hint ? "cite-hint" : ""}`}
    >
      {shown}
    </button>
  );
}
