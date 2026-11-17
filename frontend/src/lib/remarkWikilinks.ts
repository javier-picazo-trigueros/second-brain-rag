import { parseWikilinks } from "./wikilinks";

interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
}

// No se tocan los enlaces dentro de código ni dentro de otros enlaces.
const SKIP = new Set(["code", "inlineCode", "link", "linkReference", "definition", "html"]);

function replacement(text: string): MdNode[] | null {
  const links = parseWikilinks(text);
  if (links.length === 0) return null;
  const nodes: MdNode[] = [];
  let cursor = 0;
  for (const link of links) {
    if (link.index > cursor) nodes.push({ type: "text", value: text.slice(cursor, link.index) });
    const shown = link.label ?? (link.heading ? `${link.target} › ${link.heading}` : link.target);
    if (link.embed || !link.note) {
      // Incrustaciones y ficheros que no son notas: solo se nombran, nunca se cargan.
      nodes.push({
        type: "link",
        url: `wikiembed:${encodeURIComponent(link.target)}`,
        children: [{ type: "text", value: link.target }],
      });
    } else {
      const hash = link.heading ? `#${encodeURIComponent(link.heading)}` : "";
      nodes.push({
        type: "link",
        url: `wikilink:${encodeURIComponent(link.target)}${hash}`,
        children: [{ type: "text", value: shown }],
      });
    }
    cursor = link.index + link.raw.length;
  }
  if (cursor < text.length) nodes.push({ type: "text", value: text.slice(cursor) });
  return nodes;
}

function walk(node: MdNode): void {
  if (!node.children || SKIP.has(node.type)) return;
  const next: MdNode[] = [];
  for (const child of node.children) {
    const parts = child.type === "text" && child.value?.includes("[[") ? replacement(child.value) : null;
    if (parts) next.push(...parts);
    else {
      walk(child);
      next.push(child);
    }
  }
  node.children = next;
}

/** Plugin de remark: `[[Nota|etiqueta]]` pasa a ser un enlace `wikilink:` que la interfaz resuelve. */
export function remarkWikilinks() {
  return (tree: MdNode) => walk(tree);
}
