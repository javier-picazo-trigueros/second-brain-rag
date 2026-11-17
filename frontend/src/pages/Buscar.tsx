import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorBanner } from "../components/ErrorBanner";
import { FacetPanel } from "../components/FacetPanel";
import { SearchIcon, XIcon } from "../components/icons";
import { useNotePanel } from "../hooks/notePanel";
import { useSearch } from "../hooks/useSearch";
import { apiGet, type SearchNote, type SubjectInfo } from "../lib/api";
import { formatNumber } from "../lib/format";
import {
  EMPTY_FILTERS,
  filtersActive,
  filtersFromParams,
  highlight,
  paramsFromState,
  type Filters,
} from "../lib/search";

const DEBOUNCE_MS = 350;
const SNIPPET_CHARS = 260;

function snippet(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= SNIPPET_CHARS) return flat;
  return `${flat.slice(0, SNIPPET_CHARS).replace(/\s\S*$/, "")} …`;
}

function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlight(text, query).map((part, i) =>
        part.hit ? (
          <mark key={i} className="rounded bg-accent-soft px-0.5 text-text">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  );
}

function Result({ note, query }: { note: SearchNote; query: string }) {
  const { open } = useNotePanel();
  const best = note.chunks[0];
  const meta = [note.asignatura, note.curso, best?.page != null ? `p. ${best.page}` : null].filter(
    (part): part is string => Boolean(part),
  );
  return (
    <article className="rounded-xl border border-border bg-surface p-4 transition-colors hover:border-border-strong">
      <h2 className="text-base font-semibold leading-snug">
        <button
          type="button"
          onClick={() => open(note.path, best?.page ?? null)}
          className="text-left hover:underline"
        >
          {note.title}
        </button>
      </h2>
      {meta.length > 0 ? (
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          {meta.map((part) => (
            <span key={part} className="rounded bg-surface-2 px-1.5 py-0.5">
              {part}
            </span>
          ))}
        </p>
      ) : null}
      {best ? (
        <>
          {best.heading_path ? <p className="mt-2 text-xs text-muted">{best.heading_path}</p> : null}
          <p className="mt-1 text-sm leading-6">
            <Marked text={snippet(best.text)} query={query} />
          </p>
        </>
      ) : null}
      {note.tags.length > 0 ? (
        <ul aria-label="Etiquetas" className="mt-2 flex flex-wrap gap-1.5">
          {note.tags.slice(0, 6).map((tag) => (
            <li key={tag} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
              {tag}
            </li>
          ))}
        </ul>
      ) : null}
      {note.also_in.length > 0 ? (
        <p className="mt-2 text-xs text-muted">
          También en {note.also_in.length} {note.also_in.length === 1 ? "ubicación" : "ubicaciones"}
        </p>
      ) : null}
    </article>
  );
}

export function Buscar() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const inputRef = useRef<HTMLInputElement>(null);

  // El texto escrito aún no confirmado; si la URL cambia desde fuera (Atrás), manda la URL.
  const [draft, setDraft] = useState({ base: query, text: query });
  const text = draft.base === query ? draft.text : query;
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [subjects, setSubjects] = useState<SubjectInfo[]>([]);

  useEffect(() => {
    let cancelled = false;
    apiGet<SubjectInfo[]>("/subjects")
      .then((list) => !cancelled && setSubjects(list))
      .catch(() => undefined); // los atajos son un extra: sin ellos se puede buscar igual
    return () => {
      cancelled = true;
    };
  }, []);

  function commit(nextText: string, nextFilters: Filters, replace = false) {
    setParams(paramsFromState(nextText, nextFilters), { replace });
  }

  // Busca sola un momento después de dejar de escribir.
  useEffect(() => {
    if (text.trim() === query.trim()) return;
    const timer = setTimeout(() => commit(text, filters, true), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `commit` solo depende de setParams, estable en la práctica
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, query, filters]);

  const state = useSearch(query, filters);
  const activeCount = filters.asignaturas.length + filters.cursos.length + filters.tags.length;
  const facets = state.status === "ready" ? state.data.facets : { asignaturas: [], cursos: [], tags: [] };
  const hasFacets = facets.asignaturas.length + facets.cursos.length + facets.tags.length > 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-5">
        <h1 className="text-2xl font-semibold tracking-tight">Buscar</h1>

        <form
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            commit(text, filters);
          }}
          className="mt-4 flex items-center gap-2 rounded-[22px] border border-border bg-surface px-4 py-1.5 shadow-[var(--shadow)] transition-colors focus-within:border-accent"
        >
          <SearchIcon size={18} className="shrink-0 text-muted" />
          <label htmlFor="buscar-input" className="sr-only">
            Buscar en tus apuntes
          </label>
          <input
            id="buscar-input"
            ref={inputRef}
            type="search"
            value={text}
            placeholder="Busca por tema, concepto o frase…"
            onChange={(event) => setDraft({ base: query, text: event.target.value })}
            className="composer-input min-w-0 flex-1 bg-transparent py-2 text-base outline-none placeholder:text-muted [&::-webkit-search-cancel-button]:hidden"
          />
          {text !== "" ? (
            <button
              type="button"
              aria-label="Borrar la búsqueda"
              onClick={() => {
                setDraft({ base: "", text: "" });
                commit("", filters);
                inputRef.current?.focus();
              }}
              className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-text"
            >
              <XIcon size={16} />
            </button>
          ) : null}
        </form>

        {query.trim() === "" ? (
          <section aria-label="Empezar" className="mt-8">
            <p className="text-muted">
              {filtersActive(filters)
                ? `Escribe algo para buscar en ${filters.asignaturas.join(", ") || "estos filtros"}.`
                : "Busca en todos tus apuntes a la vez, sin necesitar una pregunta completa."}
            </p>
            {subjects.length > 0 ? (
              <div className="mt-5">
                <h2 className="mb-2 text-sm font-semibold">Explorar por asignatura</h2>
                <ul className="flex flex-wrap gap-2">
                  {subjects.map((subject) => (
                    <li key={subject.name}>
                      <button
                        type="button"
                        onClick={() => {
                          commit("", { ...EMPTY_FILTERS, asignaturas: [subject.name] });
                          inputRef.current?.focus();
                        }}
                        className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm transition-colors hover:border-border-strong hover:bg-surface-2"
                      >
                        {subject.name} ({formatNumber(subject.notes)})
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        ) : (
          <div className="mt-6 grid gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
            <div>
              <button
                type="button"
                aria-expanded={filtersOpen}
                aria-controls="buscar-filtros"
                onClick={() => setFiltersOpen((v) => !v)}
                className="mb-3 rounded-lg border border-border-strong px-3 py-1.5 text-sm md:hidden"
              >
                Filtros{activeCount > 0 ? ` (${activeCount})` : ""}
              </button>
              <div id="buscar-filtros" className={`${filtersOpen ? "block" : "hidden"} md:block`}>
                {hasFacets || filtersActive(filters) ? (
                  <FacetPanel facets={facets} filters={filters} onChange={(next) => commit(text, next)} />
                ) : null}
              </div>
            </div>

            <section aria-label="Resultados" className="min-w-0">
              <p role="status" className="mb-3 text-sm text-muted">
                {state.status === "loading"
                  ? "Buscando…"
                  : state.status === "ready"
                    ? `${state.data.notes.length} ${state.data.notes.length === 1 ? "nota" : "notas"}`
                    : ""}
              </p>
              {state.status === "error" ? <ErrorBanner message={state.error.message} /> : null}
              {state.status === "ready" && state.data.notes.length === 0 ? (
                <div className="rounded-xl border border-border bg-surface-2 p-5">
                  <p>Ninguna nota encaja con «{query}»{filtersActive(filters) ? " y esos filtros" : ""}.</p>
                </div>
              ) : null}
              {state.status === "ready" ? (
                <ol className="space-y-3">
                  {state.data.notes.map((note) => (
                    <li key={note.path}>
                      <Result note={note} query={query} />
                    </li>
                  ))}
                </ol>
              ) : null}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
