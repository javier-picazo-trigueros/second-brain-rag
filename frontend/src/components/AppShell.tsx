import { useCallback, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { ConversationProvider, useConversation } from "../hooks/conversation";
import { NoteContext } from "../hooks/notePanel";
import { SessionProvider } from "../hooks/session";
import { applyTheme, loadTheme, nextTheme, saveTheme, THEME_LABEL, type Theme } from "../lib/theme";
import { ActivityIcon, MenuIcon, MessageIcon, MonitorIcon, MoonIcon, SunIcon } from "./icons";
import { NotePanel } from "./NotePanel";

const NAV = [
  { to: "/", label: "Preguntar", Icon: MessageIcon, end: true },
  { to: "/estado", label: "Estado", Icon: ActivityIcon, end: false },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("nav-collapsed") === "1";
  } catch {
    return false;
  }
}

const THEME_ICON = { system: MonitorIcon, light: SunIcon, dark: MoonIcon } as const;

function History() {
  const { turns } = useConversation();
  if (turns.length === 0) return null;
  return (
    <section aria-label="Esta sesión" className="mt-6 min-h-0 flex-1 overflow-y-auto">
      <h2 className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted">Esta sesión</h2>
      <ol className="space-y-0.5">
        {turns.map((turn, index) => (
          <li key={index}>
            <Link
              to={{ pathname: "/", hash: `#pregunta-${index}` }}
              title={turn.question}
              className="block truncate rounded-md px-3 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text"
            >
              {turn.question}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [note, setNote] = useState<{ path: string; page: number | null } | null>(null);

  const open = useCallback((path: string, page: number | null) => setNote({ path, page }), []);
  const close = useCallback(() => setNote(null), []);

  function toggleNav() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("nav-collapsed", next ? "1" : "0");
    } catch {
      // sin almacenamiento: la preferencia solo dura la sesión
    }
  }

  function cycleTheme() {
    const next = nextTheme(theme);
    setTheme(next);
    saveTheme(next);
    applyTheme(next);
  }

  const ThemeIcon = THEME_ICON[theme];

  return (
    <SessionProvider>
      <NoteContext.Provider value={{ open, close }}>
        <ConversationProvider>
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-fg"
        >
          Saltar al contenido
        </a>
        <div className="flex h-dvh bg-bg text-text">
          <nav
            aria-label="Principal"
            className={`flex shrink-0 flex-col border-r border-border bg-surface p-2 ${collapsed ? "w-16" : "w-60"}`}
          >
            <button
              type="button"
              onClick={toggleNav}
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expandir navegación" : "Contraer navegación"}
              className="mb-2 flex h-10 items-center gap-3 rounded-md px-3 text-muted hover:bg-surface-2 hover:text-text"
            >
              <MenuIcon size={18} />
              {collapsed ? null : <span className="font-semibold text-text">Segundo cerebro</span>}
            </button>
            <ul className="space-y-1">
              {NAV.map(({ to, label, Icon, end }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    end={end}
                    aria-label={label}
                    className={({ isActive }: { isActive: boolean }) =>
                      `flex h-10 items-center gap-3 rounded-md px-3 ${
                        isActive ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-text"
                      }`
                    }
                  >
                    <Icon size={18} />
                    {collapsed ? null : <span>{label}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
            {collapsed ? <div className="flex-1" /> : <History />}
            <button
              type="button"
              onClick={cycleTheme}
              aria-label={`${THEME_LABEL[theme]}. Cambiar`}
              className="mt-auto flex h-10 items-center gap-3 rounded-md px-3 text-muted hover:bg-surface-2 hover:text-text"
            >
              <ThemeIcon size={18} />
              {collapsed ? null : <span>{THEME_LABEL[theme]}</span>}
            </button>
          </nav>

          <main id="contenido" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto">
            <Outlet />
          </main>

          {note ? (
            <div className="w-full max-w-xl shrink-0 border-l border-border max-md:fixed max-md:inset-0 max-md:z-40 max-md:max-w-none">
              <NotePanel path={note.path} page={note.page} onClose={close} onOpenNote={open} />
            </div>
          ) : null}
        </div>
        </ConversationProvider>
      </NoteContext.Provider>
    </SessionProvider>
  );
}
