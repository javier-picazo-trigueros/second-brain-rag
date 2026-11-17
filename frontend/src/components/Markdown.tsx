import type { ComponentProps, ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

/**
 * Esquema de saneado: el predeterminado más el protocolo interno `cite:` (los chips de cita) y las
 * clases `language-*` de los bloques de código, para el resaltado. Nunca se renderiza HTML en crudo.
 */
const schema = {
  ...defaultSchema,
  protocols: { ...defaultSchema.protocols, href: [...(defaultSchema.protocols?.href ?? []), "cite"] },
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ["className", /^language-[\w-]+$/]],
  },
};

export function urlTransform(url: string): string {
  return url.startsWith("cite:") ? url : defaultUrlTransform(url);
}

export function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

/** Los encabezados «Página N» de los apuntes convertidos de PDF reciben un ancla `pagina-N`. */
export function pageAnchor(text: string): string | undefined {
  const match = text.trim().match(/^p[áa]gina\s+(\d+)$/i);
  return match ? `pagina-${match[1]}` : undefined;
}

type Components = NonNullable<ComponentProps<typeof ReactMarkdown>["components"]>;

function heading(Tag: "h1" | "h2" | "h3" | "h4" | "h5" | "h6") {
  return function Heading({ children }: { children?: ReactNode }) {
    return <Tag id={pageAnchor(textOf(children))}>{children}</Tag>;
  };
}

export const noteComponents: Components = {
  h1: heading("h1"),
  h2: heading("h2"),
  h3: heading("h3"),
  h4: heading("h4"),
  h5: heading("h5"),
  h6: heading("h6"),
  a: ({ href, children }) => <ExternalLink href={href}>{children}</ExternalLink>,
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
}

export function Markdown({ children, components = noteComponents, highlight = false }: MarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={highlight ? [[rehypeSanitize, schema], rehypeHighlight] : [[rehypeSanitize, schema]]}
      urlTransform={urlTransform}
      components={components}
    >
      {children}
    </ReactMarkdown>
  );
}
