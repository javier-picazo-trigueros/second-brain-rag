import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useSearch } from "../hooks/useSearch";
import { EMPTY_FILTERS } from "../lib/search";
import { notePath } from "../lib/wikilinks";
import { SearchIcon } from "./icons";

interface Props {
  open: boolean;
  onClose: () => void;
  onNewConversation: () => void;
}

interface Option {
  key: string;
  label: string;
  hint?: string;
  run: () => void;
}

const NOTES_SHOWN = 8;
const DEBOUNCE_MS = 200;

/**
 * Paleta Ctrl+K: salta a una pantalla, empieza una conversación o busca una nota sin salir de lo
 * que se está haciendo. Patrón «combobox» con lista (WAI-ARIA): el foco se queda en el campo y la
 * opción activa se anuncia con `aria-activedescendant`.
 */
export function CommandPalette({ open, onClose, onNewConversation }: Props) {
  return open ? <Palette onClose={onClose} onNewConversation={onNewConversation} /> : null;
}

function Palette({ onClose, onNewConversation }: Omit<Props, "open">) {
  const navigate = useNavigate();
  const id = useId();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const text = query.trim();

  // El foco vuelve a donde estaba al cerrar.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => before?.focus?.();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(text), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  const search = useSearch(debounced, EMPTY_FILTERS);
  const current = debounced === text; // los resultados son de lo que hay escrito ahora

  const options = useMemo<Option[]>(() => {
    const go = (to: string | { pathname: string; search: string }) => () => {
      onClose();
      navigate(to);
    };
    if (text === "") {
      return [
        { key: "preguntar", label: "Preguntar", run: go("/") },
        { key: "buscar", label: "Buscar", run: go("/buscar") },
        { key: "estado", label: "Estado", run: go("/estado") },
        {
          key: "nueva",
          label: "Nueva conversación",
          run: () => {
            onClose();
            onNewConversation();
          },
        },
      ];
    }
    const notes =
      current && search.status === "ready"
        ? search.data.notes.slice(0, NOTES_SHOWN).map((note) => ({
            key: note.path,
            label: note.title,
            hint: [note.asignatura, note.curso].filter(Boolean).join(" · "),
            run: go(notePath(note.path)),
          }))
        : [];
    const all = {
      key: "__todos",
      label: `Ver todos los resultados de «${text}»`,
      run: go({ pathname: "/buscar", search: `?${new URLSearchParams({ q: text })}` }),
    };
    return [...notes, all];
  }, [text, current, search, navigate, onClose, onNewConversation]);

  const selected = Math.min(active, options.length - 1);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((selected + step + options.length) % options.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      options[selected]?.run();
    } else if (event.key === "Tab") {
      event.preventDefault(); // un solo elemento enfocable: el foco no sale del diálogo
    }
  }

  let status = "";
  if (text !== "") {
    if (!current || search.status === "loading") status = "Buscando…";
    else if (search.status === "ready" && search.data.notes.length === 0) status = `Sin resultados para «${text}».`;
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center px-4 pt-[12vh]">
      <div data-testid="palette-backdrop" aria-hidden="true" className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Buscar o ir a…"
        onKeyDown={onKeyDown}
        className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-border px-4">
          <SearchIcon size={18} />
          <input
            ref={input}
            role="combobox"
            aria-label="Buscar en tus apuntes o ir a una pantalla"
            aria-expanded="true"
            aria-controls={`${id}-lista`}
            aria-activedescendant={`${id}-${selected}`}
            aria-autocomplete="list"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="Busca una nota o escribe una pantalla…"
            className="h-12 w-full bg-transparent text-[0.9375rem] outline-none placeholder:text-muted"
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-xs text-muted sm:block">Esc</kbd>
        </div>

        {search.status === "error" && current && text !== "" ? (
          <div role="alert" className="border-b border-border bg-caution-bg px-4 py-2 text-sm text-caution-fg">
            {search.error.message}
          </div>
        ) : null}

        <ul id={`${id}-lista`} role="listbox" aria-label="Resultados" className="max-h-80 overflow-y-auto p-1.5">
          {options.map((option, index) => (
            <li
              key={option.key}
              id={`${id}-${index}`}
              role="option"
              aria-selected={index === selected}
              onMouseMove={() => setActive(index)}
              onClick={option.run}
              className={`flex cursor-pointer items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-sm ${
                index === selected ? "bg-accent-soft text-accent" : "hover:bg-surface-2"
              }`}
            >
              <span className="truncate">{option.label}</span>
              {option.hint ? <span className="shrink-0 text-xs text-muted">{option.hint}</span> : null}
            </li>
          ))}
        </ul>
        <p role="status" aria-live="polite" className="min-h-0 px-4 pb-2 text-xs text-muted empty:hidden">
          {status}
        </p>
      </div>
    </div>
  );
}
