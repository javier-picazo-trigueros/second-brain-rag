/**
 * El modelo a veces escribe código dentro de delimitadores de fórmula (`\[ \text{char* a[] = {...};} \]`)
 * y KaTeX lo pintaría como matemáticas (llaves como agrupadores, texto duplicado en HTML+MathML).
 * Aquí se decide si el cuerpo de una «fórmula» es en realidad código, y se le quita el envoltorio.
 */

// Órdenes de LaTeX que solo aparecen en matemáticas: si hay alguna, es una fórmula.
const MATH_COMMANDS =
  /\\(?:frac|dfrac|sum|int|prod|sqrt|cdot|times|div|pm|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|phi|omega|Delta|Sigma|Omega|infty|leq?|geq?|neq|approx|equiv|lim|log|ln|sin|cos|tan|exp|mathbb|mathbf|mathcal|mathrm|left|right|begin|end|vec|hat|bar|overline|partial|nabla|forall|exists|in|notin|subset|subseteq|cup|cap|to|rightarrow|Rightarrow|leftrightarrow|binom|choose|bmod|pmod|ldots|cdots)(?![a-zA-Z])/;

// Señales de código: literales de cadena, `;` de fin de sentencia, llamadas, directivas, operadores de C.
const CODE_SIGNS =
  /"[^"\n]*"|;\s*(?:[}\\]|$)|\b[A-Za-z_]\w*\s*\([^()\n]*\)\s*;|#include|#define|\b(?:int|void|char|float|double|return|printf|scanf|malloc|free|sizeof)\b[\s(*]|\bfor\s*\(|\bwhile\s*\(|\bif\s*\(.*\)\s*[{;]|->|&&|\|\||!=|==/;

/** Cuerpo sin el `\text{...}` con el que el modelo envuelve el código. */
export function codeOf(body: string): string {
  let text = body.trim();
  const wrapped = /^\\(?:text|texttt|mathtt)\s*\{([\s\S]*)\}$/.exec(text);
  if (wrapped?.[1] !== undefined) text = wrapped[1].trim();
  return text;
}

export function looksLikeCode(body: string): boolean {
  const inner = codeOf(body);
  if (MATH_COMMANDS.test(inner.replace(/^\\text\s*\{/, ""))) return false;
  return CODE_SIGNS.test(inner);
}
