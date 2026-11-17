import { pagesLabel, type CitationRef } from "../lib/answer";
import { HelpIcon } from "./icons";

interface Props {
  citation: CitationRef;
  onOpen: (path: string, page: number | null) => void;
}

const BASE =
  "inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 align-baseline text-sm leading-5 " +
  "transition-colors duration-150";

const UNVERIFIED_HELP =
  "Esta nota no estaba entre las fuentes consultadas; el modelo la nombró por su cuenta.";

function pagesName(pages: number[]): string {
  if (pages.length === 0) return "";
  if (pages.length === 1) return `, página ${pages[0]}`;
  return `, páginas ${pages.slice(0, -1).join(", ")} y ${pages[pages.length - 1]}`;
}

export function CitationChip({ citation, onOpen }: Props) {
  if (citation.kind === "unverified") {
    const name = citation.label ? `Cita no verificada: ${citation.label}` : "Cita no verificada";
    // La explicación va en `title` (descripción accesible y tooltip), nunca como texto dentro del
    // párrafo: así no puede aparecer mezclada con la respuesta.
    return (
      <span
        role="note"
        tabIndex={0}
        data-kind="unverified"
        aria-label={name}
        title={UNVERIFIED_HELP}
        className={`${BASE} border-dashed border-caution-border bg-caution-bg text-caution-fg`}
      >
        <HelpIcon size={13} />
        <span className="truncate">{citation.label || "cita no verificada"}</span>
      </span>
    );
  }

  const hint = citation.hint;
  const kind = hint ? "hint" : "evidence";
  const tone = hint
    ? "border-border bg-surface-2 text-muted hover:border-border-strong"
    : "border-transparent bg-accent-soft text-accent hover:border-accent";
  const pages = pagesLabel(citation.pages);

  const content = (
    <>
      <span className="truncate">{citation.label}</span>
      {pages ? <span aria-hidden="true">·</span> : null}
      {pages ? <span>{pages}</span> : null}
    </>
  );

  if (citation.path === null) {
    return (
      <span data-kind={kind} className={`${BASE} ${tone}`}>
        {content}
      </span>
    );
  }

  const target = citation.path;
  const verb = hint ? `Ver también «${citation.label}»` : `Abrir «${citation.label}»`;
  return (
    <button
      type="button"
      data-kind={kind}
      aria-label={`${verb}${pagesName(citation.pages)}`}
      onClick={() => onOpen(target, citation.pages[0] ?? null)}
      className={`${BASE} ${tone} cursor-pointer`}
    >
      {content}
    </button>
  );
}
