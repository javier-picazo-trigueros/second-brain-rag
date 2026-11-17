import { slugify, uniqueSlugger } from "./wikilinks";

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function textOf(node: HastNode): string {
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(textOf).join("");
}

/** Pone un `id` a cada encabezado (`pagina-7` para «Página 7», si no su slug) tras el saneado. */
export function rehypeHeadingIds() {
  return (tree: HastNode) => {
    const unique = uniqueSlugger();
    const visit = (node: HastNode): void => {
      if (node.type === "element" && node.tagName && /^h[1-6]$/.test(node.tagName)) {
        const text = textOf(node);
        const slug = slugify(text);
        if (slug !== "") node.properties = { ...node.properties, id: unique(slug) };
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}
