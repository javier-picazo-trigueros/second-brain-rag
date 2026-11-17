import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ErrorBanner } from "../components/ErrorBanner";
import { NoteContent } from "../components/NoteContent";
import { encodeNotePath } from "../components/NotePanel";
import { ApiError, apiGet, type NoteDetail } from "../lib/api";
import { headingsOf, notePath } from "../lib/wikilinks";

type Loaded =
  | { path: string; status: "error"; error: Error }
  | { path: string; status: "ready"; note: NoteDetail };

/** La nota a pantalla completa: índice de encabezados, enlaces resueltos y enlaces entrantes. */
export function Nota() {
  const path = useParams()["*"] ?? "";
  const [params] = useSearchParams();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const state = useMemo(
    () => (loaded !== null && loaded.path === path ? loaded : ({ status: "loading" } as const)),
    [loaded, path],
  );

  useEffect(() => {
    let cancelled = false;
    apiGet<NoteDetail>(`/notes/${encodeNotePath(path)}`)
      .then((note) => !cancelled && setLoaded({ path, status: "ready", note }))
      .catch((error: Error) => !cancelled && setLoaded({ path, status: "error", error }));
    return () => {
      cancelled = true;
    };
  }, [path]);

  const page = Number(params.get("p")) || null;
  const targetId = hash ? decodeURIComponent(hash.slice(1)) : page ? `pagina-${page}` : null;
  useEffect(() => {
    if (state.status !== "ready" || targetId === null) return;
    document.getElementById(targetId)?.scrollIntoView({ block: "start" });
  }, [state.status, targetId]);

  const toc = useMemo(
    () => (state.status === "ready" ? headingsOf(state.note.body).filter((h) => h.level <= 3) : []),
    [state],
  );

  const open = (target: string, heading: string | null) =>
    navigate(`${notePath(target)}${heading ? `#${heading}` : ""}`);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-6xl gap-10 px-4 py-6 sm:px-5">
        <div className="min-w-0 max-w-3xl flex-1">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="mb-4 rounded-md px-1.5 py-1 text-sm text-muted hover:bg-surface-2 hover:text-text"
          >
            ← Volver
          </button>

          {state.status === "loading" ? (
            <div role="status" aria-live="polite">
              <span className="sr-only">Cargando nota…</span>
              <div className="skeleton mb-3 h-8 w-2/3" />
              <div className="skeleton mb-2 h-4 w-full" />
              <div className="skeleton mb-2 h-4 w-5/6" />
              <div className="skeleton h-4 w-2/3" />
            </div>
          ) : null}

          {state.status === "error" ? (
            state.error instanceof ApiError && state.error.status !== 0 && state.error.status < 500 ? (
              <div className="rounded-xl border border-border bg-surface-2 p-5">
                <p>{state.error.message}</p>
                <Link to="/buscar" className="mt-3 inline-block text-accent underline underline-offset-2">
                  Buscar en tus apuntes
                </Link>
              </div>
            ) : (
              <ErrorBanner message={state.error.message} />
            )
          ) : null}

          {state.status === "ready" ? (
            <NoteContent note={state.note} titleLevel={1} onOpenNote={open} />
          ) : null}
        </div>

        {toc.length > 0 ? (
          <aside className="sticky top-6 hidden max-h-[calc(100dvh-3rem)] w-60 shrink-0 self-start overflow-y-auto xl:block">
            <nav aria-label="Índice de la nota">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">En esta nota</h2>
              <ul className="space-y-1 border-l border-border text-sm">
                {toc.map((h) => (
                  <li key={h.slug} style={{ paddingLeft: `${(h.level - 1) * 0.75 + 0.75}rem` }}>
                    <a href={`#${h.slug}`} className="block py-0.5 text-muted hover:text-text">
                      {h.text}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
