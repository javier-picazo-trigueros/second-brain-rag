import { createContext, useContext, useState, type MouseEvent, type ReactNode } from "react";

import { notePath, slugify } from "../lib/wikilinks";

export interface WikiLinkApi {
  /** Destino de cada [[enlace]] -> notas candidatas (vacío: no existe; varias: ambiguo). */
  resolved: Record<string, string[]>;
  /** Abre una nota, opcionalmente en un apartado (slug del encabezado). */
  open: (path: string, heading: string | null) => void;
}

export const WikiLinkContext = createContext<WikiLinkApi>({ resolved: {}, open: () => {} });

function parse(href: string): { target: string; heading: string | null } {
  const body = href.slice("wikilink:".length);
  const hash = body.indexOf("#");
  const target = decodeURIComponent(hash === -1 ? body : body.slice(0, hash));
  const heading = hash === -1 ? null : slugify(decodeURIComponent(body.slice(hash + 1)));
  return { target, heading: heading || null };
}

const BASE = "rounded px-0.5 underline decoration-dotted underline-offset-2";

/** Un `[[enlace]]` de una nota: abre la nota, pregunta cuál si es ambiguo o se ve como no existente. */
export function WikiLink({ href, children }: { href: string; children?: ReactNode }) {
  const { resolved, open } = useContext(WikiLinkContext);
  const [choosing, setChoosing] = useState(false);
  const { target, heading } = parse(href);
  const candidates = resolved[target] ?? [];

  if (candidates.length === 0) {
    return (
      <span data-state="missing" title="No existe en el vault" className="text-muted italic">
        {children}
      </span>
    );
  }

  if (candidates.length === 1) {
    const path = candidates[0]!;
    const to = `${notePath(path)}${heading ? `#${heading}` : ""}`;
    const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) return; // pestaña nueva
      event.preventDefault();
      open(path, heading);
    };
    return (
      <a href={to} onClick={onClick} className={`${BASE} text-accent hover:bg-accent-soft`}>
        {children}
      </a>
    );
  }

  return (
    <span
      className="relative inline-block"
      onKeyDown={(event) => {
        if (event.key === "Escape") setChoosing(false);
      }}
    >
      <button
        type="button"
        aria-expanded={choosing}
        aria-haspopup="true"
        onClick={() => setChoosing((v) => !v)}
        className={`${BASE} text-accent hover:bg-accent-soft`}
      >
        {children}
      </button>
      {choosing ? (
        <span
          role="group"
          aria-label="¿Cuál de estas notas?"
          className="absolute left-0 top-full z-20 mt-1 flex w-max max-w-[20rem] flex-col rounded-xl border border-border bg-surface p-1 text-left text-sm shadow-[var(--shadow)]"
        >
          {candidates.map((path) => (
            <button
              key={path}
              type="button"
              onClick={() => {
                setChoosing(false);
                open(path, heading);
              }}
              className="break-words rounded-lg px-2.5 py-1.5 text-left hover:bg-surface-2"
            >
              {path}
            </button>
          ))}
        </span>
      ) : null}
    </span>
  );
}

/** Incrustaciones (`![[...]]`) y ficheros que no son notas: se nombran, no se cargan. */
export function WikiEmbed({ children }: { children?: ReactNode }) {
  return (
    <span data-state="embed" title="Contenido incrustado: no se carga aquí" className="text-muted italic">
      {children}
    </span>
  );
}
