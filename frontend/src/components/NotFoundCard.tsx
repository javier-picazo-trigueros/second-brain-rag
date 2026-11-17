import { useId } from "react";

import type { FragmentInfo } from "../lib/api";
import { citedSources, pagesLabel } from "../lib/answer";
import { InfoIcon } from "./icons";

const FIXED_SENTENCE = "No lo encuentro en el vault.";

/** Lo que el modelo añadió tras la frase fija (normalmente «Podrías mirar: [S2]»). */
export function splitNotFound(answer: string): string {
  const text = answer.trim();
  return text.startsWith(FIXED_SENTENCE) ? text.slice(FIXED_SENTENCE.length).trim() : text;
}

interface Props {
  answer: string;
  fragments: FragmentInfo[];
  evidenceCount: number;
  lowConfidence: boolean;
  onOpenNote: (path: string, page: number | null) => void;
  onRephrase: () => void;
  /** Solo existe cuando la pantalla Buscar está disponible. */
  onSearch?: () => void;
}

const BUTTON =
  "rounded-md border border-border-strong bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2";

/** «No lo encuentro en el vault»: un resultado legítimo, no un error. Tono sereno, sin rojo. */
export function NotFoundCard({
  answer,
  fragments,
  evidenceCount,
  lowConfidence,
  onOpenNote,
  onRephrase,
  onSearch,
}: Props) {
  const titleId = useId();
  const nearby = citedSources(splitNotFound(answer), fragments);
  return (
    <section
      aria-labelledby={titleId}
      className="rounded-md border border-border bg-surface-2 p-5"
    >
      <div className="flex items-start gap-3">
        <span className="mt-1 text-muted">
          <InfoIcon size={20} />
        </span>
        <div className="min-w-0 space-y-3">
          <h2 id={titleId} className="text-lg font-semibold">
            No lo encuentro en tus apuntes
          </h2>
          <p className="text-muted">
            He mirado {evidenceCount === 1 ? "1 nota" : `${evidenceCount} notas`} y ninguna lo trata con
            claridad.
            {lowConfidence ? " Tu pregunta se parece poco a lo que hay en tus apuntes." : ""}
          </p>
          {nearby.length > 0 ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Notas cercanas</h3>
              <ul className="flex flex-wrap gap-2">
                {nearby.map((note) => (
                  <li key={note.path} className="max-w-full">
                    <button
                      type="button"
                      onClick={() => onOpenNote(note.path, note.pages[0] ?? null)}
                      className="inline-flex max-w-full items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm transition-colors hover:border-border-strong hover:bg-surface-2"
                    >
                      <span className="truncate">{note.label}</span>{" "}
                      {note.pages.length > 0 ? (
                        <span className="whitespace-nowrap text-xs text-muted">{pagesLabel(note.pages)}</span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1">
            <button type="button" className={BUTTON} onClick={onRephrase}>
              Reformular la pregunta
            </button>
            {onSearch ? (
              <button type="button" className={BUTTON} onClick={onSearch}>
                Buscar esto en tus apuntes
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
