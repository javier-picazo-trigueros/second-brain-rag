export type Theme = "system" | "light" | "dark";

const KEY = "theme";
const THEMES: readonly Theme[] = ["system", "light", "dark"];

/** Lee la preferencia guardada. El almacenamiento puede estar bloqueado: nunca debe romper. */
export function loadTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    return THEMES.includes(saved as Theme) ? (saved as Theme) : "system";
  } catch {
    return "system";
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // sin almacenamiento: el tema solo dura esta sesión
  }
}

/** "system" quita el atributo para que decida `prefers-color-scheme`; el resto lo fuerza. */
export function applyTheme(theme: Theme): void {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

export function nextTheme(theme: Theme): Theme {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]!;
}

export const THEME_LABEL: Record<Theme, string> = {
  system: "Tema: sistema",
  light: "Tema: claro",
  dark: "Tema: oscuro",
};
