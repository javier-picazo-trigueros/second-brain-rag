// Capturas (360, 768 y 1280 px; claro y oscuro) y axe de las pantallas reales, con `/ask` y
// `/notes` simulados para poder fotografiar cada estado (aviso, «no lo encuentro», error...).
// Requiere `.\tasks.ps1 web-build` y `brain serve` (la API sirve la interfaz compilada).
//
//   node scripts/screens.mjs <carpeta-de-salida>
//
// Imprime un resumen JSON con las violaciones de axe por pantalla; las capturas van a la carpeta.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright-core";

const EDGE = process.env.BRAIN_BROWSER ?? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.BRAIN_UI_URL ?? "http://127.0.0.1:8000/";
const [, , outDir] = process.argv;
if (!outDir) {
  console.error("Uso: node scripts/screens.mjs <carpeta-de-salida>");
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const TIMINGS = { retrieval_ms: 148, first_token_ms: 1240, total_ms: 5030, llm_load_ms: 5, tokens_per_second: 47 };
const frag = (id, label, path, page, kind = "evidence") => ({ id, label, path, title: label, kind, page, heading: null });
const src = (label, path, pages, kind = "evidence", extra = {}) => ({
  label, path, title: label, kind, pages, asignatura: "Estructuras de Datos", curso: "3º", truncated: false, ...extra,
});
const sse = (events) => events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join("");

const FRAGMENTS = [
  frag("S1", "Tema 1 · Complejidad y análisis", "Estructuras/Tema 1.md", 3),
  frag("S2", "Tema 1 · Complejidad y análisis", "Estructuras/Tema 1.md", 5),
  frag("S3", "Tema 2 · Listas, pilas y colas", "Estructuras/Tema 2.md", 1),
  frag("S4", "Tema 4 · Árboles", "Estructuras/Tema 4.md", 6),
  frag("S5", "Tema 5 · Hashing y grafos", "Estructuras/Tema 5.md", 9),
];
const SOURCES = [
  src("Tema 1 · Complejidad y análisis", "Estructuras/Tema 1.md", [3, 5]),
  src("Tema 2 · Listas, pilas y colas", "Estructuras/Tema 2.md", [1]),
  src("Tema 4 · Árboles", "Estructuras/Tema 4.md", [6]),
  src("Tema 5 · Hashing y grafos", "Estructuras/Tema 5.md", [9]),
  src("Test en clases · Repaso", "Estructuras/Repaso.md", [2], "evidence", { truncated: true }),
];
const ANSWER =
  "Estructuras de Datos trata de cómo organizar la información en memoria para que las operaciones más habituales sean eficientes [S1].\n\n" +
  "**Bloques principales**\n\n" +
  "- **Análisis de la complejidad.** Notación asintótica, mejor y peor caso [S1][S2].\n" +
  "- **Estructuras lineales.** Listas enlazadas, pilas y colas y cuándo conviene cada una [S3].\n" +
  "- **Árboles y montículos.** Árboles binarios de búsqueda y colas de prioridad [S4].\n" +
  "- **Tablas hash y grafos.** Colisiones, recorridos y caminos mínimos [S5].\n\n" +
  "**Qué destacaría**\n\n" +
  "- Elegir la estructura según las operaciones que más se usan [S1].\n" +
  "- Las prácticas piden implementar cada estructura desde cero [cita no verificada: S9].";
const done = (over) => ({
  type: "done", answer: "", citations: [], invalid: [], warnings: [], not_found: false,
  confidence: "alta", similarity: 0.71, timings: TIMINGS, prompt_tokens: 3166, completion_tokens: 430, ...over,
});
const sources = (over = {}) => ({
  type: "sources", sources: SOURCES, fragments: FRAGMENTS, confidence: "alta", similarity: 0.71, dropped_notes: 0, ...over,
});

const ASKS = {
  respuesta: sse([
    sources(),
    { type: "token", text: ANSWER },
    done({ answer: ANSWER, citations: FRAGMENTS, invalid: ["S9"], warnings: ["citas_no_verificadas"] }),
  ]),
  confianza: sse([
    sources({ confidence: "baja", similarity: 0.57 }),
    { type: "token", text: "Solo encuentro una mención indirecta [S3]." },
    done({ answer: "Solo encuentro una mención indirecta [S3].", citations: [FRAGMENTS[2]], warnings: ["confianza_baja"], confidence: "baja", similarity: 0.57 }),
  ]),
  nolo: sse([
    sources({ sources: [SOURCES[1]], fragments: [FRAGMENTS[2]], confidence: "baja", similarity: 0.52 }),
    { type: "token", text: "No lo encuentro en el vault.\n\nPodrías mirar: [S3]" },
    done({ answer: "No lo encuentro en el vault.\n\nPodrías mirar: [S3]", not_found: true, warnings: ["confianza_baja"], confidence: "baja", similarity: 0.52, citations: [FRAGMENTS[2]] }),
  ]),
  error: sse([{ type: "error", message: "Ollama no responde en http://localhost:11434: arráncalo con `ollama serve`." }]),
};
const NOTE = {
  path: "Estructuras/Tema 1.md", title: "Tema 1 · Complejidad y análisis", asignatura: "Estructuras de Datos", curso: "3º",
  frontmatter: {}, tags: ["complejidad", "analisis"], concepts: ["notacion-asintotica", "caso-peor"], links: [],
  body: "# Complejidad\n\nLa **complejidad** mide cuántos recursos usa un algoritmo.\n\n## Página 3\n\nNotación asintótica: $O(n)$, $\\Omega(n)$.\n\n```python\ndef suma(xs):\n    return sum(xs)\n```",
  related: [{ path: "Estructuras/Tema 2.md", title: "Tema 2 · Listas, pilas y colas", score: 1.2, via: ["complejidad"] }],
};

async function ask(page, text) {
  const box = page.getByRole("textbox", { name: "Tu pregunta" });
  await box.fill(text);
  await box.press("Enter");
  await page.getByRole("button", { name: /Cómo se ha respondido|Enviar/ }).first().waitFor();
  await page.waitForTimeout(250);
}

const scenarios = [
  { name: "inicio", run: async () => {} },
  { name: "respuesta", run: async (page) => ask(page, "¿De qué trata la asignatura de Estructuras de Datos?") },
  { name: "respuesta-nota", run: async (page) => {
      await ask(page, "¿De qué trata la asignatura de Estructuras de Datos?");
      await page.getByRole("button", { name: /Fuente 1: Tema 1/ }).first().click();
      await page.getByRole("heading", { name: /Tema 1 · Complejidad/, level: 2 }).waitFor();
  } },
  { name: "confianza-baja", run: async (page) => ask(page, "¿Qué es un montículo?") },
  { name: "no-lo-encuentro", run: async (page) => ask(page, "¿Cómo funciona el borrow checker de Rust?") },
  { name: "error", run: async (page) => { await page.getByRole("textbox", { name: "Tu pregunta" }).fill("hola"); await page.getByRole("textbox", { name: "Tu pregunta" }).press("Enter"); await page.getByRole("alert").waitFor(); } },
  { name: "estado", run: async (page) => {
      const menu = page.getByRole("button", { name: "Abrir navegación" }); // en pantallas pequeñas la navegación es un cajón
      if (await menu.isVisible()) await menu.click();
      await page.getByRole("link", { name: "Estado" }).click(); await page.getByRole("heading", { name: "Ollama" }).waitFor(); } },
];
const askFor = { respuesta: "respuesta", "respuesta-nota": "respuesta", "confianza-baja": "confianza", "no-lo-encuentro": "nolo", error: "error" };

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const summary = [];
for (const scheme of ["light", "dark"]) {
  for (const width of [360, 768, 1280]) {
    for (const scenario of scenarios) {
      const context = await browser.newContext({ viewport: { width, height: 860 }, colorScheme: scheme, reducedMotion: "reduce" });
      const page = await context.newPage();
      await page.route("**/ask", (route) =>
        route.fulfill({ status: 200, contentType: "text/event-stream", body: ASKS[askFor[scenario.name] ?? "respuesta"] }));
      await page.route("**/notes/**", (route) => route.fulfill({ json: NOTE }));
      await page.goto(BASE);
      await page.getByRole("textbox", { name: "Tu pregunta" }).waitFor();
      await scenario.run(page);
      await page.screenshot({ path: join(outDir, `${scenario.name}-${width}-${scheme}.png`) });
      const axe = await new AxeBuilder({ page }).analyze();
      summary.push({
        pantalla: scenario.name, ancho: width, tema: scheme,
        axe: axe.violations.map((v) => ({ id: v.id, impacto: v.impact, nodos: v.nodes.length, ejemplo: v.nodes[0]?.target })),
        desbordeHorizontal: await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
      });
      await context.close();
    }
  }
}
await browser.close();
writeFileSync(join(outDir, "resumen.json"), JSON.stringify(summary, null, 2));
const bad = summary.filter((s) => s.axe.length > 0 || s.desbordeHorizontal);
console.log(`${summary.length} capturas; con problemas: ${bad.length}`);
console.log(JSON.stringify(bad, null, 2));
