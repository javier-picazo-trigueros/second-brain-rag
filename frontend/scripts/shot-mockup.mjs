// Capturas del mockup estático de docs/design/preguntar.html (claro/oscuro, escritorio y móvil).
//   node scripts/shot-mockup.mjs <carpeta-de-salida>
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const EDGE = process.env.BRAIN_BROWSER ?? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const [, , outDir] = process.argv;
if (!outDir) {
  console.error("Uso: node scripts/shot-mockup.mjs <carpeta-de-salida>");
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });
const file = pathToFileURL(resolve("..", "docs", "design", "preguntar.html")).href;

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
for (const theme of ["light", "dark"]) {
  for (const [name, width, height] of [["escritorio", 1280, 900], ["movil", 390, 844]]) {
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: "reduce" }); // sin animaciones a medias
    await page.goto(`${file}?theme=${theme}`);
    await page.evaluate(() => document.fonts.ready);
    if (name === "escritorio") await page.locator(".cite button").first().focus(); // muestra el tooltip de una cita
    await page.screenshot({ path: join(outDir, `preguntar-${theme}-${name}.png`) });
    await page.close();
  }
}
await browser.close();
