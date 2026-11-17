// Hace preguntas en la interfaz real (Vite en :5173 + `brain serve` en :8000), las mide y guarda
// capturas. Solo para comprobar a mano; no forma parte de la aplicación ni de los tests.
//
//   node scripts/ask-ui.mjs <carpeta-de-salida> "pregunta 1" "pregunta 2" ...
//
// Usa el Edge instalado (sin descargar navegadores). Imprime un JSON por pregunta.
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const EDGE = process.env.BRAIN_BROWSER ?? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.BRAIN_UI_URL ?? "http://localhost:5173/";
const [, , outDir, ...questions] = process.argv;
if (!outDir || questions.length === 0) {
  console.error('Uso: node scripts/ask-ui.mjs <carpeta-de-salida> "pregunta" ["otra pregunta" ...]');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(BASE);

for (const [index, question] of questions.entries()) {
  const started = Date.now();
  const box = page.getByRole("textbox", { name: "Tu pregunta" });
  await box.fill(question);
  await box.press("Enter");

  const turn = page.locator(`#pregunta-${index}`);
  await turn.getByRole("button", { name: /Cómo se ha respondido/ }).waitFor({ timeout: 300_000 });
  const elapsedMs = Date.now() - started;
  await turn.getByRole("button", { name: /Cómo se ha respondido/ }).click();

  const answer = await turn.locator('[data-testid="answer"], section:has(h3)').first().innerText();
  const chips = await turn.locator("[data-kind]").evaluateAll((nodes) =>
    nodes.map((n) => ({ kind: n.getAttribute("data-kind"), name: n.getAttribute("aria-label") ?? n.textContent })),
  );
  const notices = await turn.locator('[data-testid="notice"]').allInnerTexts();
  const details = await turn.getByRole("region", { name: "Cómo se ha respondido" }).innerText();
  const sources = await turn
    .locator("section")
    .filter({ hasText: "Fuentes usadas" })
    .locator("button")
    .allInnerTexts();
  await turn.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(outDir, `pregunta-${index + 1}.png`), fullPage: false });
  console.log(JSON.stringify({ question, elapsedMs, answer, chips, notices, details, sources }, null, 2));
}
await browser.close();
