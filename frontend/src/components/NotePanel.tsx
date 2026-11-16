import { useEffect, useRef, useState } from "react";

import { ApiError, apiGet, type NoteDetail } from "../lib/api";
import { ErrorBanner } from "./ErrorBanner";
import { XIcon } from "./icons";
import { Markdown } from "./Markdown";

interface Props {
  path: string;
  page?: number | null;
  onClose: () => void;
  onOpenNote: (path: string, page: number | null) => void;
}

type Loaded =
  | { path: string; status: "error"; error: ApiError | Error }
  | { path: string; status: "ready"; note: NoteDetail };

export function encodeNotePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

const CHIP = "rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-sm text-muted";

/** Panel lateral con una nota: metadatos, Markdown renderizado y relacionadas. */
export function NotePanel({ path, page = null, onClose, onOpenNote }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  // Mientras lo cargado no corresponda a la ruta pedida, se está cargando (sin setState en el efecto).
  const state = loaded !== null && loaded.path === path ? loaded : ({ status: "loading" } as const);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<NoteDetail>(`/notes/${encodeNotePath(path)}`)
      .then((note) => !cancelled && setLoaded({ path, status: "ready", note }))
      .catch((error: Error) => !cancelled && setLoaded({ path, status: "error", error }));
    return () => {
      cancelled = true;
    };
  }, [path]);

  useEffect(() => {
    closeRef.current?.focus();
  }, [path]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (state.status !== "ready" || page === null) return;
    document.getElementById(`pagina-${page}`)?.scrollIntoView({ block: "start" });
  }, [state, page]);

  return (
    <aside aria-label="Nota abierta" className="flex h-full min-h-0 flex-col bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <span className="truncate text-sm text-muted">{path}</span>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Cerrar la nota"
          className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
        >
          <XIcon size={18} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {state.status === "loading" ? (
          <div role="status" aria-live="polite">
            <span className="sr-only">Cargando nota…</span>
            <div className="skeleton mb-3 h-7 w-3/4" />
            <div className="skeleton mb-2 h-4 w-full" />
            <div className="skeleton mb-2 h-4 w-5/6" />
            <div className="skeleton h-4 w-2/3" />
          </div>
        ) : null}

        {state.status === "error" ? (
          state.error instanceof ApiError && state.error.status === 404 ? (
            <p role="status" className="rounded-md border border-border bg-surface-2 p-4 text-muted">
              {state.error.message}
            </p>
          ) : (
            <ErrorBanner message={state.error.message} />
          )
        ) : null}

        {state.status === "ready" ? <NoteBody note={state.note} onOpenNote={onOpenNote} /> : null}
      </div>
    </aside>
  );
}

function NoteBody({ note, onOpenNote }: { note: NoteDetail; onOpenNote: Props["onOpenNote"] }) {
  const meta = [note.asignatura, note.curso].filter(Boolean).join(" · ");
  return (
    <article>
      <h2 className="text-xl font-semibold leading-snug">{note.title}</h2>
      {meta ? <p className="mt-1 text-sm text-muted">{meta}</p> : null}

      {note.tags.length > 0 ? (
        <ul aria-label="Etiquetas" className="mt-3 flex flex-wrap gap-1.5">
          {note.tags.map((tag) => (
            <li key={tag} className={CHIP}>
              {tag}
            </li>
          ))}
        </ul>
      ) : null}
      {note.concepts.length > 0 ? (
        <ul aria-label="Conceptos" className="mt-2 flex flex-wrap gap-1.5">
          {note.concepts.map((concept) => (
            <li key={concept} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-sm text-accent">
              {concept}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="reading mt-5">
        <Markdown highlight>{note.body}</Markdown>
      </div>

      {note.related.length > 0 ? (
        <section aria-label="Notas relacionadas" className="mt-8 border-t border-border pt-4">
          <h3 className="mb-2 text-sm font-semibold text-muted">Relacionadas</h3>
          <ul className="space-y-1.5">
            {note.related.map((item) => (
              <li key={item.path}>
                <button
                  type="button"
                  onClick={() => onOpenNote(item.path, null)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-left hover:border-accent"
                >
                  <span className="block font-medium">{item.title}</span>
                  <span className="block text-xs text-muted">{`vía: ${item.via.join(", ")}`}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
