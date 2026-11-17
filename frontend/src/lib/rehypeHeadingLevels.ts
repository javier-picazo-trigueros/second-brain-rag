interface HastNode {
  type: string;
  tagName?: string;
  children?: HastNode[];
}

/**
 * Recoloca los encabezados de una nota bajo el título de la página: el más alto pasa a `base` y
 * ninguno salta más de un nivel respecto al anterior (axe: «heading-order»), conservando la jerarquía.
 */
export function rehypeHeadingLevels(base: number) {
  return (tree: HastNode) => {
    const headings: HastNode[] = [];
    const collect = (node: HastNode): void => {
      if (node.type === "element" && node.tagName && /^h[1-6]$/.test(node.tagName)) headings.push(node);
      node.children?.forEach(collect);
    };
    collect(tree);
    if (headings.length === 0) return;

    const original = (node: HastNode) => Number(node.tagName!.slice(1));
    const top = Math.min(...headings.map(original));
    let previous = base - 1;
    for (const node of headings) {
      const level = Math.min(original(node) - top + base, previous + 1, 6);
      node.tagName = `h${level}`;
      previous = level;
    }
  };
}
