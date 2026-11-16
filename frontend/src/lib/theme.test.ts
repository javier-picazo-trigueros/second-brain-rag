import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { applyTheme, loadTheme, nextTheme, saveTheme } from "./theme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("defaults to following the system", () => {
    expect(loadTheme()).toBe("system");
  });

  it("restores a saved choice", () => {
    saveTheme("dark");
    expect(loadTheme()).toBe("dark");
  });

  it("ignores garbage in storage", () => {
    localStorage.setItem("theme", "neón");
    expect(loadTheme()).toBe("system");
  });

  it("forcing a theme sets data-theme", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("following the system removes data-theme so the media query decides", () => {
    applyTheme("dark");
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("cycles system -> light -> dark -> system", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });

  it("still works when storage is unavailable", () => {
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("bloqueado");
    };
    try {
      expect(loadTheme()).toBe("system");
    } finally {
      Storage.prototype.getItem = original;
    }
    expect(() => {
      const setItem = Storage.prototype.setItem;
      Storage.prototype.setItem = () => {
        throw new Error("bloqueado");
      };
      try {
        saveTheme("dark");
      } finally {
        Storage.prototype.setItem = setItem;
      }
    }).not.toThrow();
  });
});
