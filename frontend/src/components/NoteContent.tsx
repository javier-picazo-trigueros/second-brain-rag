import { useState } from "react";

import type { NoteDetail } from "../lib/api";
import { CheckIcon, CopyIcon, ExternalIcon } from "./icons";
import { Markdown } from "./Markdown";
import { WikiLinkContext } from "./WikiLink";

interface Props {
  note: NoteDetail;
  /** Abre otra nota (desde un [[enlace]], las relacionadas o las que enlazan aquí). */
  onOpenNote: (path: string, heading: string | null) => void;
  /** Nivel del título: 1 en la pantalla de la nota, 2 en el panel lateral. */
  titleLevel?: 1 | 2;
}

const CHIP = "rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-sm text-muted";
const ACTION =
  "inline-flex items-center gap-1.5 rounded-lg border border-border-strong px-3 py-1.5 text-sm hover:bg-surface-2";

function CopyPath({ path }: { path: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard?.writeText(path);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // sin permiso de portapapeles: la ruta sigue visible en la cabecera
    }
  }
  return (
    <>
      <button type="button" onClick={copy} className={ACTION}>
        {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
        Copiar la ruta
      </button>
      <span aria-live="polite" className="text-sm text-muted">
        {copied ? "Copiada" : ""}
      </span>
    </>
  );
}

function NoteList({
  label,
  items,
  hint,
  onOpen,
}: {
  label: string;
  items: { path: string; title: string; note?: string }[];
  hint?: string;
  onOpen: (path: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section aria-label={label} className="mt-8 border-t border-border pt-4">
      <h3 className="mb-2 text-sm font-semibold text-muted">{label}</h3>
      {hint ? <p className="mb-2 text-xs text-muted">{hint}</p> : null}
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.path}>
            <button
              type="button"
              onClick={() => onOpen(item.path)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left hover:border-accent"
            >
              <span className="block font-medium">{item.title}</span>
              {item.note ? <span className="block text-xs text-muted">{item.note}</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Cuerpo de una nota (metadatos, texto con sus [[enlaces]], relacionadas y enlaces entrantes). */
export function NoteContent({ note, onOpenNote, titleLevel = 2 }: Props) {
  const Title = titleLevel === 1 ? "h1" : "h2";
  const meta = [note.asignatura, note.curso].filter(Boolean).join(" · ");
  return (
    <article>
      <Title className={`${titleLevel === 1 ? "text-3xl" : "text-xl"} font-semibold leading-snug tracking-tight`}>
        {note.title}
      </Title>
      {meta ? <p className="mt-1 text-sm text-muted">{meta}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <a href={note.obsidian_url} className={ACTION}>
          <ExternalIcon size={14} />
          Abrir en Obsidian
        </a>
        <CopyPath path={note.path} />
      </div>

      {note.tags.length > 0 ? (
        <ul aria-label="Etiquetas" className="mt-3 flex flex-wrap gap-1.5">
          {note.tags.map((tag) => (
            <li key={tag} className={CHIP}>
              {tag}
            </li>
          ))}
        </ul>
      ) : null}
      {note.concepts.length > 0 ? (
        <ul aria-label="Conceptos" className="mt-2 flex flex-wrap gap-1.5">
          {note.concepts.map((concept) => (
            <li key={concept} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-sm text-accent">
              {concept}
            </li>
          ))}
        </ul>
      ) : null}

      <WikiLinkContext.Provider value={{ resolved: note.resolved_links, open: onOpenNote }}>
        <div className="reading mt-5">
          <Markdown highlight wikilinks headingBase={titleLevel + 1}>
            {note.body}
          </Markdown>
        </div>
      </WikiLinkContext.Provider>

      <NoteList
        label="Relacionadas"
        items={note.related.map((r) => ({ path: r.path, title: r.title, note: `vía: ${r.via.join(", ")}` }))}
        onOpen={(path) => onOpenNote(path, null)}
      />
      <NoteList
        label="Notas que enlazan aquí"
        items={note.backlinks}
        onOpen={(path) => onOpenNote(path, null)}
      />
    </article>
  );
}
