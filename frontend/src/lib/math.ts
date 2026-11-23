import "katex/dist/katex.min.css"; // fuentes y estilos empaquetados por Vite: nada sale a una CDN
import rehypeKatex, { type Options } from "rehype-katex";
import remarkMath from "remark-math";

import { remarkMathAsCode } from "./remarkMathAsCode";

/**
 * Fórmulas LaTeX con KaTeX. Este módulo se carga bajo demanda (import dinámico desde `Markdown`)
 * solo cuando el texto lleva delimitadores de fórmula, para no pesar en el arranque.
 */
// El código que el modelo envuelve en delimitadores de fórmula se devuelve a código antes de KaTeX.
export const remarkMathPlugins = [remarkMath, remarkMathAsCode];

/** `trust` apagado: sin `\href`, `\url`, `\includegraphics` ni `\htmlClass`; TeX inválido no rompe. */
const OPTIONS: Options = { trust: false, strict: "ignore", output: "htmlAndMathml" };
export const rehypeKatexPlugin: [typeof rehypeKatex, Options] = [rehypeKatex, OPTIONS];

// Lo que nunca se toca: código en bloque (``` o ~~~) o en línea, y los enlaces de cita
// `[título \[MD\] · p. 3](cite:0)`, cuyo texto lleva corchetes escapados que no son fórmulas.
const PROTECTED =
  /(^|\n)(```|~~~)[^\n]*\n[\s\S]*?(?:\n\2[^\n]*(?=\n|$)|$)|`[^`\n]*`|\[(?:[^[\]\\]|\\.)*\]\(cite:\d+\)/g;

/**
 * `$$x$$` solo en su línea pasa a bloque, como en Obsidian. Con `latex`, que es solo para las
 * respuestas del modelo, `\( x \)` y `\[ x \]` pasan a `$x$` y `$$x$$` (remark-math solo entiende
 * estos). En una nota no: allí `\[` es un corchete escapado, igual que en Obsidian.
 */
export function normalizeDelimiters(text: string, latex = false): string {
  const convert = (part: string) => {
    const block = part.replace(
      /^[ \t]*\$\$([^\n$]+?)\$\$[ \t]*$/gm,
      (_m, body: string) => `$$\n${body.trim()}\n$$`,
    );
    return latex
      ? block
          .replace(/\\\[([\s\S]+?)\\\]/g, (_m, body: string) => `\n\n$$\n${body.trim()}\n$$\n\n`)
          .replace(/\\\(([\s\S]+?)\\\)/g, (_m, body: string) => `$${body.trim()}$`)
      : block;
  };
  let out = "";
  let last = 0;
  for (const match of text.matchAll(PROTECTED)) {
    out += convert(text.slice(last, match.index)) + match[0];
    last = match.index + match[0].length;
  }
  return out + convert(text.slice(last));
}
