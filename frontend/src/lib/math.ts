import "katex/dist/katex.min.css"; // fuentes y estilos empaquetados por Vite: nada sale a una CDN
import rehypeKatex, { type Options } from "rehype-katex";
import remarkMath from "remark-math";

/**
 * Fórmulas LaTeX con KaTeX. Este módulo se carga bajo demanda (import dinámico desde `Markdown`)
 * solo cuando el texto lleva delimitadores de fórmula, para no pesar en el arranque.
 */
export const remarkMathPlugin = remarkMath;

/** `trust` apagado: sin `\href`, `\url`, `\includegraphics` ni `\htmlClass`; TeX inválido no rompe. */
const OPTIONS: Options = { trust: false, strict: "ignore", output: "htmlAndMathml" };
export const rehypeKatexPlugin: [typeof rehypeKatex, Options] = [rehypeKatex, OPTIONS];

// Código en bloque (``` o ~~~) o en línea: los delimitadores de su interior no se tocan.
const CODE = /(^|\n)(```|~~~)[^\n]*\n[\s\S]*?(?:\n\2[^\n]*(?=\n|$)|$)|`[^`\n]*`/g;

/**
 * Los modelos suelen escribir `\( x \)` y `\[ x \]`; remark-math entiende `$x$` y `$$x$$`.
 * Se convierten fuera del código. Un `$$x$$` solo en su línea pasa a bloque, como en Obsidian.
 */
export function normalizeDelimiters(text: string): string {
  const convert = (part: string) =>
    part
      .replace(/^[ \t]*\$\$([^\n$]+?)\$\$[ \t]*$/gm, (_m, body: string) => `$$\n${body.trim()}\n$$`)
      .replace(/\\\[([\s\S]+?)\\\]/g, (_m, body: string) => `\n$$\n${body.trim()}\n$$\n`)
      .replace(/\\\(([\s\S]+?)\\\)/g, (_m, body: string) => `$${body.trim()}$`);
  let out = "";
  let last = 0;
  for (const match of text.matchAll(CODE)) {
    out += convert(text.slice(last, match.index)) + match[0];
    last = match.index + match[0].length;
  }
  return out + convert(text.slice(last));
}
