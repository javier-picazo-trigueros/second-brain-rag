import type { SourceInfo } from "../lib/api";
import { FileIcon } from "./icons";

interface Props {
  sources: SourceInfo[];
  onOpen: (path: string, page: number | null) => void;
}

function metaParts(source: SourceInfo): string[] {
  const pages = source.pages.length > 0 ? `p. ${source.pages.join(", ")}` : null;
  return [source.asignatura, source.curso, pages].filter((part): part is string => Boolean(part));
}

const CARD =
  "flex w-full flex-col gap-1 rounded-md border border-border bg-surface p-3 text-left " +
  "transition-colors duration-150 hover:border-accent";

export function SourceCards({ sources, onOpen }: Props) {
  const evidence = sources.filter((s) => s.kind === "evidence");
  const hints = sources.filter((s) => s.kind === "hint");
  if (sources.length === 0) return null;

  return (
    <div className="mt-6 space-y-5">
      {evidence.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-muted">Fuentes usadas ({evidence.length})</h3>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {evidence.map((source) => (
              <li key={source.path}>
                <button
                  type="button"
                  className={CARD}
                  onClick={() => onOpen(source.path, source.pages[0] ?? null)}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <FileIcon size={15} />
                    <span className="min-w-0 break-words">{source.label}</span>
                  </span>{" "}
                  <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    {metaParts(source).map((part) => (
                      <span key={part} className="rounded bg-surface-2 px-1.5 py-0.5">
                        {part}
                      </span>
                    ))}
                    {source.truncated ? <span className="italic">recortada para caber</span> : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {hints.length > 0 ? (
        <section aria-label="Notas relacionadas (pistas)">
          <h3 className="text-sm font-semibold text-muted">Notas relacionadas</h3>
          <p className="mb-2 text-xs text-muted">
            Pistas automáticas por conceptos compartidos; no son evidencia de la respuesta.
          </p>
          <ul className="flex flex-wrap gap-2">
            {hints.map((source) => (
              <li key={source.path}>
                <button
                  type="button"
                  onClick={() => onOpen(source.path, null)}
                  className="rounded-full border border-border bg-surface-2 px-3 py-1 text-sm text-muted hover:border-border-strong hover:text-text"
                >
                  {source.label}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
