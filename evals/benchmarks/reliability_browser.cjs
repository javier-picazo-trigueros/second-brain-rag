const { createRequire } = require('node:module');
const path = require('node:path');
const frontend = path.resolve('frontend');
const { chromium } = createRequire(path.join(frontend, 'package.json'))('playwright-core');

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const external = [];
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'http://127.0.0.1:5173') {
        external.push(url.hostname);
        return route.abort();
      }
      if (/^\/assets\/[\w.-]+$/.test(url.pathname)) {
        return route.fulfill({ path: path.join(frontend, 'dist', url.pathname.slice(1)) });
      }
      if (url.pathname === '/notes/A.md') {
        return route.fulfill({ json: {
          path: 'A.md', title: 'A', body: '![a](https://remote.invalid/a) ![b](//remote.invalid/b)',
          tags: [], concepts: [], links: [], backlinks: [], related: [], resolved_links: {}, frontmatter: {},
          obsidian_url: ''
        } });
      }
      if (route.request().isNavigationRequest()) return route.fulfill({ path: path.join(frontend,'dist/index.html') });
      return route.fulfill({ json: {} });
    });
    await page.goto('http://127.0.0.1:5173/nota/A.md');
    const markers = page.getByText('imagen externa bloqueada', {exact:true});
    await markers.first().waitFor();
    await page.waitForLoadState('networkidle');
    const count = await markers.count();
    const elements = await page.locator('img[src*="remote.invalid"],link[href*="remote.invalid"]').count();
    console.log({ blockedMarkers: count, externalRequests: external.length, externalElements: elements });
    if (count !== 2 || elements || external.length) throw Error('Fallo al bloquear imágenes');
  } finally {
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exitCode = 1});
