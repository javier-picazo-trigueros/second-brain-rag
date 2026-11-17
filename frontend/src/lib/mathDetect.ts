/** ¿Lleva el texto algo que parezca una fórmula? Evita cargar KaTeX para texto sin ellas. */
export function mayHaveMath(text: string): boolean {
  return text.includes("$") || text.includes("\\(") || text.includes("\\[");
}
