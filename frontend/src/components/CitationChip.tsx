import { useId } from "react";

import type { CitationRef } from "../lib/answer";
import { HelpIcon } from "./icons";

interface Props {
  citation: CitationRef;
  onOpen: (path: string, page: number | null) => void;
}

const BASE =
  "inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 align-baseline text-sm leading-5 " +
  "transition-colors duration-150";

/** Primera página de «7», «7-9», «7, 9» o «7 y 9»: a la que se abre la nota. */
function firstPage(page: string | null): number | null {
  const match = page?.match(/\d+/);
  return match ? Number(match[0]) : null;
}

export function CitationChip({ citation, onOpen }: Props) {
  const descriptionId = useId();

  if (citation.kind === "unverified") {
    const name = citation.label ? `Cita no verificada: ${citation.label}` : "Cita no verificada";
    return (
      <span
        role="note"
        tabIndex={0}
        data-kind="unverified"
        aria-label={name}
        aria-describedby={descriptionId}
        title="Esta nota no estaba entre las fuentes consultadas; el modelo la nombró por su cuenta."
        className={`${BASE} border-dashed border-caution-border bg-caution-bg text-caution-fg`}
      >
        <HelpIcon size={13} />
        <span className="truncate">{citation.label || "cita no verificada"}</span>
        <span id={descriptionId} className="sr-only">
          Esta nota no estaba entre las fuentes consultadas; el modelo la nombró por su cuenta.
        </span>
      </span>
    );
  }

  const hint = citation.hint;
  const kind = hint ? "hint" : "evidence";
  const tone = hint
    ? "border-border bg-surface-2 text-muted hover:border-border-strong"
    : "border-transparent bg-accent-soft text-accent hover:border-accent";
  const page = citation.page;

  const pageText =
    page === null ? null : (
      <span className={citation.pageVerified ? undefined : "underline decoration-dotted underline-offset-2"}>
        p. {page}
        {citation.pageVerified ? null : <span aria-hidden="true">?</span>}
      </span>
    );

  if (citation.path === null) {
    return (
      <span data-kind={kind} className={`${BASE} ${tone}`}>
        <span className="truncate">{citation.label}</span>
        {pageText}
      </span>
    );
  }

  const target = citation.path;
  const verb = hint ? `Ver también «${citation.label}»` : `Abrir «${citation.label}»`;
  const pageName =
    page === null ? "" : citation.pageVerified ? `, página ${page}` : `, página ${page} no verificada`;

  return (
    <button
      type="button"
      data-kind={kind}
      data-page-verified={citation.pageVerified ? "true" : "false"}
      aria-label={`${verb}${pageName}`}
      onClick={() => onOpen(target, firstPage(page))}
      className={`${BASE} ${tone} cursor-pointer`}
    >
      <span className="truncate">{citation.label}</span>
      {page === null ? null : <span aria-hidden="true">·</span>}
      {pageText}
    </button>
  );
}
