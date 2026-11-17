export interface Filters {
  asignaturas: string[];
  cursos: string[];
  tags: string[];
}

export const EMPTY_FILTERS: Filters = { asignaturas: [], cursos: [], tags: [] };

export function filtersActive(filters: Filters): boolean {
  return filters.asignaturas.length + filters.cursos.length + filters.tags.length > 0;
}

export function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

/** Filtros de la URL: `asig`, `curso` y `tag` repetidos (O dentro de cada uno, Y entre ellos). */
export function filtersFromParams(params: URLSearchParams): Filters {
  return {
    asignaturas: params.getAll("asig"),
    cursos: params.getAll("curso"),
    tags: params.getAll("tag"),
  };
}

export function paramsFromState(query: string, filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query);
  for (const value of filters.asignaturas) params.append("asig", value);
  for (const value of filters.cursos) params.append("curso", value);
  for (const value of filters.tags) params.append("tag", value);
  return params;
}

export interface Segment {
  text: string;
  hit: boolean;
}

const MIN_WORD = 3; // las palabras más cortas («de», «la») marcarían medio texto

/** Una letra sin su acento ni su mayúscula, conservando el largo (1 a 1 con el texto original). */
function fold(char: string): string {
  const base = char.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  return base.length === 1 ? base : char.toLowerCase().slice(0, 1) || char;
}

/**
 * Parte `text` en trozos marcando las palabras de la consulta, sin distinguir mayúsculas ni
 * acentos. La consulta es texto, nunca un patrón.
 */
export function highlight(text: string, query: string): Segment[] {
  if (text === "") return [];
  const words = [...new Set(query.split(/\s+/).map((w) => [...w].map(fold).join("")))].filter(
    (w) => w.length >= MIN_WORD && /[\p{L}\p{N}]/u.test(w),
  );
  if (words.length === 0) return [{ text, hit: false }];

  const folded = [...text].map(fold).join("");
  const marked = new Array<boolean>(text.length).fill(false);
  for (const word of words) {
    let from = folded.indexOf(word);
    while (from !== -1) {
      for (let i = from; i < from + word.length; i++) marked[i] = true;
      from = folded.indexOf(word, from + 1);
    }
  }

  const segments: Segment[] = [];
  let start = 0;
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || marked[i] !== marked[start]) {
      segments.push({ text: text.slice(start, i), hit: marked[start]! });
      start = i;
    }
  }
  return segments;
}

/** El texto de un fragmento sin las marcas de Markdown, para mostrarlo como una frase corrida. */
export function plainSnippet(markdown: string): string {
  return markdown
    .replace(/!\[\[[^\]]*\]\]/g, " ") // incrustaciones de Obsidian
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ") // imágenes
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?\|([^\]]+)\]\]/g, "$2") // [[destino|etiqueta]]
    .replace(/\[\[([^\]|#]+)(?:#[^\]]*)?\]\]/g, "$1") // [[destino]] y [[destino#apartado]]
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // [texto](url)
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/`+/g, "")
    .replace(/\*{1,3}/g, "")
    .replace(/(?<![\p{L}\p{N}])_{1,3}|_{1,3}(?![\p{L}\p{N}])/gu, "")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
