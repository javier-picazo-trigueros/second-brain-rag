import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { rehypeHeadingIds } from "../lib/rehypeHeadingIds";
import { mayHaveMath } from "../lib/mathDetect"; // ligero: KaTeX solo se carga si hace falta
import { rehypeHeadingLevels } from "../lib/rehypeHeadingLevels";
import { remarkWikilinks } from "../lib/remarkWikilinks";
import { WikiEmbed, WikiLink } from "./WikiLink";

// Protocolos internos: `cite:` (chips de cita) y los de `[[enlaces]]` e incrustaciones de las notas.
const INTERNAL = ["cite", "wikilink", "wikiembed"] as const;

/**
 * Esquema de saneado: el predeterminado más los protocolos internos y las clases `language-*` de los
 * bloques de código, para el resaltado. Nunca se renderiza HTML en crudo.
 */
const schema = {
  ...defaultSchema,
  protocols: { ...defaultSchema.protocols, href: [...(defaultSchema.protocols?.href ?? []), ...INTERNAL] },
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ["className", /^(?:language-[\w-]+|math-inline|math-display)$/]],
  },
};

export function urlTransform(url: string): string {
  return INTERNAL.some((scheme) => url.startsWith(`${scheme}:`)) ? url : defaultUrlTransform(url);
}

export function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

type Components = NonNullable<ComponentProps<typeof ReactMarkdown>["components"]>;

export const noteComponents: Components = {
  a: ({ href, children }) => {
    if (href?.startsWith("wikilink:")) return <WikiLink href={href}>{children}</WikiLink>;
    if (href?.startsWith("wikiembed:")) return <WikiEmbed>{children}</WikiEmbed>;
    return <ExternalLink href={href}>{children}</ExternalLink>;
  },
};

export function ExternalLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (!href) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

interface MarkdownProps {
  children: string;
  components?: Components;
  highlight?: boolean;
  /** `[[enlaces]]` de Obsidian como enlaces a notas (solo en notas, no en las respuestas). */
  wikilinks?: boolean;
  /** Nivel del encabezado más alto del texto (p. ej. 2 bajo un `h1`); sin él, se respetan los niveles. */
  headingBase?: number;
  /** Acepta `\( \)` y `\[ \]` como fórmulas: solo para las respuestas del modelo, no para notas. */
  latexDelimiters?: boolean;
}

type MathModule = typeof import("../lib/math");

/** Carga KaTeX (y su CSS y fuentes locales) solo la primera vez que un texto lleva fórmulas. */
function useMath(text: string): MathModule | null {
  const wanted = mayHaveMath(text);
  const [math, setMath] = useState<MathModule | null>(null);
  useEffect(() => {
    if (!wanted || math !== null) return;
    let cancelled = false;
    void import("../lib/math").then((m) => !cancelled && setMath(m));
    return () => {
      cancelled = true;
    };
  }, [wanted, math]);
  return wanted ? math : null;
}

export function Markdown({
  children,
  components = noteComponents,
  highlight = false,
  wikilinks = false,
  headingBase,
  latexDelimiters = false,
}: MarkdownProps) {
  const math = useMath(children);
  return (
    <ReactMarkdown
      remarkPlugins={[
        remarkGfm,
        ...(math ? math.remarkMathPlugins : []),
        ...(wikilinks ? [remarkWikilinks] : []),
      ]}
      rehypePlugins={[
        [rehypeSanitize, schema],
        rehypeHeadingIds, // tras el saneado, que cambiaría los ids
        ...(headingBase ? [() => rehypeHeadingLevels(headingBase)] : []),
        ...(math ? [math.rehypeKatexPlugin] : []), // tras el saneado: su HTML es generado, no del texto
        ...(highlight ? [rehypeHighlight] : []),
      ]}
      urlTransform={urlTransform}
      components={components}
    >
      {math ? math.normalizeDelimiters(children, latexDelimiters) : children}
    </ReactMarkdown>
  );
}
