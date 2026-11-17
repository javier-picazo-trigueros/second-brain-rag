import { useEffect, useMemo, useState } from "react";

import { apiPost, type SearchResponse } from "../lib/api";
import type { Filters } from "../lib/search";

export const RESULTS = 20;

type Loaded = { key: string; data: SearchResponse } | { key: string; error: Error };

export type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: SearchResponse }
  | { status: "error"; error: Error };

/**
 * Busca (sin LLM ni grafo) lo que dicen la consulta y los filtros. Una respuesta tardía de una
 * consulta anterior se descarta: el estado se asocia a la clave de lo que se pidió.
 */
export function useSearch(query: string, filters: Filters): SearchState {
  const text = query.trim();
  const key = useMemo(() => JSON.stringify([text, filters]), [text, filters]);
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (text === "") return;
    const controller = new AbortController();
    apiPost<SearchResponse>(
      "/search",
      {
        query: text,
        k: RESULTS,
        graph: false,
        asignaturas: filters.asignaturas,
        cursos: filters.cursos,
        tags: filters.tags,
      },
      { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setLoaded({ key, data });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setLoaded({ key, error });
      });
    return () => controller.abort();
  }, [text, filters, key]);

  if (text === "") return { status: "idle" };
  if (loaded === null || loaded.key !== key) return { status: "loading" };
  return "error" in loaded ? { status: "error", error: loaded.error } : { status: "ready", data: loaded.data };
}
