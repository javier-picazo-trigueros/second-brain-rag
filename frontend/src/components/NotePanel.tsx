import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, apiGet, type NoteDetail } from "../lib/api";
import { Link } from "react-router-dom";

import { notePath } from "../lib/wikilinks";
import { ErrorBanner } from "./ErrorBanner";
import { XIcon } from "./icons";
import { NoteContent } from "./NoteContent";

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

/** Panel lateral con una nota: metadatos, Markdown renderizado y relacionadas. */
export function NotePanel({ path, page = null, onClose, onOpenNote }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  // Mientras lo cargado no corresponda a la ruta pedida, se está cargando (sin setState en el efecto).
  const state = useMemo(
    () => (loaded !== null && loaded.path === path ? loaded : ({ status: "loading" } as const)),
    [loaded, path],
  );
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
        <Link
          to={`${notePath(path)}${page ? `?p=${page}` : ""}`}
          onClick={onClose}
          className="ml-auto shrink-0 rounded-md px-2 py-1 text-sm text-accent hover:bg-surface-2"
        >
          Abrir completa
        </Link>
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

        {state.status === "ready" ? (
          <NoteContent note={state.note} onOpenNote={(target) => onOpenNote(target, null)} />
        ) : null}
      </div>
    </aside>
  );
}
