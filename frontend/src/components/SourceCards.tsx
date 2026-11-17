import { useId, useState } from "react";

import { pagesLabel, type CitedSource } from "../lib/answer";
import type { SourceInfo } from "../lib/api";
import { FileIcon } from "./icons";

interface Props {
  sources: SourceInfo[];
  /** Notas citadas en el texto, con el número de su chip. */
  cited: CitedSource[];
  onOpen: (path: string, page: number | null) => void;
}

const CHIP =
  "inline-flex max-w-full items-center gap-2 rounded-full border border-border bg-surface py-1.5 pl-1.5 pr-3 " +
  "text-sm transition-colors duration-150 hover:border-border-strong hover:bg-surface-2";

function metaParts(source: SourceInfo): string[] {
  const pages = source.pages.length > 0 ? `p. ${source.pages.join(", ")}` : null;
  return [source.asignatura, source.curso, pages].filter((part): part is string => Boolean(part));
}

/** Fuentes bajo la respuesta: una fila compacta con las citadas y, plegadas, las demás. */
export function SourceCards({ sources, cited, onOpen }: Props) {
  const [expanded, setExpanded] = useState(false);
  const moreId = useId();
  if (sources.length === 0) return null;

  const citedPaths = new Set(cited.map((c) => c.path));
  const others = sources.filter((s) => !citedPaths.has(s.path));
  const nothingCited = cited.length === 0;
  const row = nothingCited ? [] : cited;
  const unnumbered = nothingCited ? others.filter((s) => s.kind === "evidence") : [];
  const extra = nothingCited ? others.filter((s) => s.kind === "hint") : others;
  const total = nothingCited ? unnumbered.length : cited.length;

  return (
    <section aria-label="Fuentes" className="mt-6">
      <div className="mb-2 flex items-center justify-between text-sm text-muted">
        <h2 className="font-normal">Fuentes · {total}</h2>
        {extra.length > 0 ? (
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={moreId}
            onClick={() => setExpanded((v) => !v)}
            className="rounded-md px-1.5 py-0.5 hover:bg-surface-2 hover:text-text"
          >
            {expanded ? "Ver menos" : `Ver todas (${extra.length} más)`}
          </button>
        ) : null}
      </div>

      <ul className="flex flex-wrap gap-2">
        {row.map((c) => (
          <li key={c.path} className="max-w-full">
            <button
              type="button"
              onClick={() => onOpen(c.path, c.pages[0] ?? null)}
              className={CHIP}
            >
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-surface-2 px-1 text-xs font-semibold text-muted">
                {c.number}
              </span>{" "}
              <span className="truncate" style={{ maxWidth: "30ch" }} title={c.label}>
                {c.label}
              </span>{" "}
              {c.pages.length > 0 ? <span className="whitespace-nowrap text-xs text-muted">{pagesLabel(c.pages)}</span> : null}
            </button>
          </li>
        ))}
        {unnumbered.map((s) => (
          <li key={s.path} className="max-w-full">
            <button
              type="button"
              onClick={() => onOpen(s.path, s.pages[0] ?? null)}
              className={CHIP}
            >
              <FileIcon size={15} />
              <span className="truncate" style={{ maxWidth: "30ch" }} title={s.label}>
                {s.label}
              </span>{" "}
              <span className="flex flex-wrap items-center gap-1 text-xs text-muted">
                {metaParts(s).map((part) => (
                  <span key={part}>{part}</span>
                ))}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {expanded && extra.length > 0 ? (
        <section id={moreId} aria-label="Otras notas consultadas" className="mt-3">
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {extra.map((s) => (
              <li key={s.path}>
                <button
                  type="button"
                  onClick={() => onOpen(s.path, s.pages[0] ?? null)}
                  className="flex w-full flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-left hover:border-border-strong"
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <FileIcon size={15} />
                    <span className="min-w-0 break-words">{s.label}</span>
                  </span>{" "}
                  <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    {s.kind === "hint" ? <span className="italic">pista por conceptos compartidos</span> : null}
                    {metaParts(s).map((part) => (
                      <span key={part} className="rounded bg-surface-2 px-1.5 py-0.5">
                        {part}
                      </span>
                    ))}
                    {s.truncated ? <span className="italic">recortada para caber</span> : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
