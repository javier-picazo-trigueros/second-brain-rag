import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import config from "../../vite.config";

it("proxies every endpoint used by the frontend client", () => {
  const files = Object.keys(import.meta.glob("../**/*.{ts,tsx}")).filter(
    (path) => !path.includes(".test.") && !path.includes("/test/"),
  );
  const routes = new Set<string>();
  for (const file of files) {
    const source = readFileSync(new URL(file, import.meta.url), "utf8");
    for (const match of source.matchAll(/(?:apiGet|apiPost)(?:<[^>]+>)?\(\s*["`](\/\w+)|request\("POST", "(\/\w+)/g)) {
      routes.add(match[1] ?? match[2]!);
    }
  }
  expect(routes.size).toBeGreaterThan(5);
  for (const path of routes) expect(config.server?.proxy, path).toHaveProperty(path);
});
