import { useCallback, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { ConversationProvider, useConversation } from "../hooks/conversation";
import { NoteContext } from "../hooks/notePanel";
import { SessionProvider } from "../hooks/session";
import { applyTheme, loadTheme, nextTheme, saveTheme, THEME_LABEL, type Theme } from "../lib/theme";
import { ActivityIcon, MenuIcon, MessageIcon, MonitorIcon, MoonIcon, SunIcon, XIcon } from "./icons";
import { NotePanel } from "./NotePanel";

// «Buscar» entra aquí cuando exista esa pantalla.
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

function History({ onNavigate }: { onNavigate: () => void }) {
  const { turns } = useConversation();
  if (turns.length === 0) return <div className="flex-1" />;
  return (
    <section aria-label="Esta sesión" className="mt-5 min-h-0 flex-1 overflow-y-auto">
      <h2 className="px-3 pb-1 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted">Esta sesión</h2>
      <ol className="space-y-0.5">
        {turns.map((turn, index) => (
          <li key={index}>
            <Link
              to={{ pathname: "/", hash: `#pregunta-${index}` }}
              title={turn.question}
              onClick={onNavigate}
              className="block truncate rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text"
            >
              {turn.question}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Shell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [navOpen, setNavOpen] = useState(false); // solo en pantallas pequeñas (cajón)
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [note, setNote] = useState<{ path: string; page: number | null } | null>(null);
  const { reset } = useConversation();
  const navigate = useNavigate();

  const open = useCallback((path: string, page: number | null) => setNote({ path, page }), []);
  const close = useCallback(() => setNote(null), []);
  const closeNav = useCallback(() => setNavOpen(false), []);

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

  function newConversation() {
    reset();
    navigate("/");
    setNavOpen(false);
  }

  const ThemeIcon = THEME_ICON[theme];
  const hideLabel = collapsed ? "md:hidden" : "";
  const row = "flex h-10 items-center gap-3 rounded-lg px-3";

  return (
    <NoteContext.Provider value={{ open, close }}>
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-fg"
      >
        Saltar al contenido
      </a>
      <div className="flex h-dvh bg-bg text-text">
        {navOpen ? (
          <div className="fixed inset-0 z-30 bg-black/40 md:hidden" aria-hidden="true" onClick={closeNav} />
        ) : null}

        <nav
          aria-label="Principal"
          className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col gap-1 border-r border-border bg-surface p-2.5 transition-transform duration-200 md:static md:translate-x-0 ${
            navOpen ? "translate-x-0" : "-translate-x-full"
          } ${collapsed ? "md:w-16" : "md:w-64"}`}
        >
          <div className="flex items-center justify-between">
            <span className={`flex items-center gap-2.5 px-2.5 py-2 font-semibold tracking-tight ${hideLabel}`}>
              <i aria-hidden="true" className="inline-block h-[22px] w-[22px] rounded-[7px] bg-accent" />
              Segundo cerebro
            </span>
            <button
              type="button"
              onClick={toggleNav}
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Expandir navegación" : "Contraer navegación"}
              className="hidden rounded-lg p-2.5 text-muted hover:bg-surface-2 hover:text-text md:block"
            >
              <MenuIcon size={18} />
            </button>
            <button
              type="button"
              onClick={closeNav}
              aria-label="Cerrar el menú"
              className="rounded-lg p-2.5 text-muted hover:bg-surface-2 md:hidden"
            >
              <XIcon size={18} />
            </button>
          </div>

          <button
            type="button"
            onClick={newConversation}
            aria-label="Nueva conversación"
            className={`${row} border border-border bg-surface text-sm transition-colors hover:bg-surface-2`}
          >
            <span aria-hidden="true" className="w-[18px] text-center text-lg leading-none">
              +
            </span>
            <span className={hideLabel}>Nueva conversación</span>
          </button>

          <ul className="mt-2 space-y-0.5">
            {NAV.map(({ to, label, Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  aria-label={label}
                  onClick={closeNav}
                  className={({ isActive }: { isActive: boolean }) =>
                    `${row} text-[0.9375rem] ${
                      isActive ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-text"
                    }`
                  }
                >
                  <Icon size={18} />
                  <span className={hideLabel}>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>

          {collapsed ? <div className="hidden flex-1 md:block" /> : null}
          <div className={collapsed ? "min-h-0 flex-1 md:hidden" : "flex min-h-0 flex-1 flex-col"}>
            <History onNavigate={closeNav} />
          </div>

          <button
            type="button"
            onClick={cycleTheme}
            aria-label={`${THEME_LABEL[theme]}. Cambiar`}
            className={`${row} text-sm text-muted hover:bg-surface-2 hover:text-text`}
          >
            <ThemeIcon size={18} />
            <span className={hideLabel}>{THEME_LABEL[theme]}</span>
          </button>
        </nav>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-border px-3 py-2 md:hidden">
            <button
              type="button"
              onClick={() => setNavOpen((v) => !v)}
              aria-expanded={navOpen}
              aria-label={navOpen ? "Cerrar navegación" : "Abrir navegación"}
              className="rounded-lg p-2 text-muted hover:bg-surface-2"
            >
              <MenuIcon size={20} />
            </button>
            <span className="font-semibold tracking-tight">Segundo cerebro</span>
            <span className="w-9" aria-hidden="true" />
          </header>
          <main id="contenido" tabIndex={-1} className="relative min-h-0 flex-1 overflow-hidden">
            <Outlet />
          </main>
        </div>

        {note ? (
          <div className="w-full max-w-xl shrink-0 border-l border-border max-md:fixed max-md:inset-0 max-md:z-50 max-md:max-w-none">
            <NotePanel path={note.path} page={note.page} onClose={close} onOpenNote={open} />
          </div>
        ) : null}
      </div>
    </NoteContext.Provider>
  );
}

export function AppShell() {
  return (
    <SessionProvider>
      <ConversationProvider>
        <Shell />
      </ConversationProvider>
    </SessionProvider>
  );
}
