/** `[[enlaces]]` de Obsidian: se interpretan igual que en el indexador (src/secondbrain/ingest). */

export interface Wikilink {
  raw: string;
  index: number;
  target: string; // ruta escrita, sin apartado ni etiqueta
  heading: string | null;
  label: string | null;
  embed: boolean; // ![[...]]
  note: boolean; // false si apunta a una imagen, un PDF, etc.
}

const NON_NOTE = new Set([
  "pdf", "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico",
  "mp3", "wav", "ogg", "m4a", "mp4", "webm", "mov", "mkv",
  "docx", "doc", "pptx", "ppt", "xlsx", "xls", "zip", "csv", "excalidraw",
]); // prettier-ignore

const PATTERN = /(!?)\[\[([^\]|#^\n]+)(?:([#^])([^\]|\n]*))?(?:\|([^\]\n]*))?\]\]/g;

export function parseWikilinks(text: string): Wikilink[] {
  const found: Wikilink[] = [];
  for (const match of text.matchAll(PATTERN)) {
    const written = match[2]!.trim();
    if (written === "") continue;
    const target = written;
    const dot = target.lastIndexOf(".");
    const extension = dot === -1 ? "" : target.slice(dot + 1).toLowerCase();
    found.push({
      raw: match[0],
      index: match.index ?? 0,
      target,
      heading: match[3] === "#" ? match[4]!.trim() || null : null,
      label: match[5]?.trim() || null,
      embed: match[1] === "!",
      note: !NON_NOTE.has(extension),
    });
  }
  return found;
}

/** Ruta de la pantalla de una nota: cada segmento codificado, las barras intactas. */
export function notePath(path: string): string {
  return `/nota/${path.split("/").map(encodeURIComponent).join("/")}`;
}

export function slugify(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export interface Heading {
  level: number;
  text: string;
  slug: string;
}

/** Hace únicos los identificadores de los encabezados repetidos: `ejemplo`, `ejemplo-2`... */
export function uniqueSlugger(): (base: string) => string {
  const seen = new Map<string, number>();
  return (base) => {
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return count === 1 ? base : `${base}-${count}`;
  };
}

export function headingsOf(markdown: string): Heading[] {
  const unique = uniqueSlugger();
  const out: Heading[] = [];
  let fence: string | null = null;
  for (const line of markdown.split(/\r?\n/)) {
    const marker = line.match(/^\s{0,3}(```|~~~)/)?.[1];
    if (marker) {
      fence = fence === null ? marker : fence === marker ? null : fence;
      continue;
    }
    if (fence !== null) continue;
    const match = line.match(/^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$/);
    if (!match) continue;
    const text = match[2]!.replace(/[*_`]/g, "").trim();
    if (text === "") continue;
    out.push({ level: match[1]!.length, text, slug: unique(slugify(text)) });
  }
  return out;
}
