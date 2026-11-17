import { codeOf, looksLikeCode } from "./mathCode";

interface MdastNode {
  type: string;
  value?: string;
  lang?: string | null;
  meta?: string | null;
  children?: MdastNode[];
}

/**
 * Tras `remark-math`: los nodos de fórmula cuyo contenido es código pasan a ser código (bloque o en
 * línea), para que KaTeX no lo reescriba. Lo que es una fórmula de verdad no se toca.
 */
export function remarkMathAsCode() {
  return (tree: MdastNode) => {
    const walk = (node: MdastNode): void => {
      node.children?.forEach((child, index) => {
        if ((child.type === "math" || child.type === "inlineMath") && looksLikeCode(child.value ?? "")) {
          const value = codeOf(child.value ?? "");
          node.children![index] =
            child.type === "math"
              ? { type: "code", lang: null, meta: null, value }
              : { type: "inlineCode", value };
        } else {
          walk(child);
        }
      });
    };
    walk(tree);
  };
}
