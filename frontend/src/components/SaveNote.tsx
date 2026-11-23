import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  previewGenerated,
  saveGenerated,
  type GeneratedPreview,
  type GeneratedSaved,
} from "../lib/api";
import { ExternalIcon } from "./icons";

interface Props {
  /** Los apuntes completos (Markdown, con sus `[S#]`). */
  markdown: string;
  subject: string | null;
  topic: number | null;
  /** Rutas de las notas de las que salen (evidencia). */
  sources: string[];
}

type Stage =
  | { name: "loading" }
  | { name: "ready"; preview: GeneratedPreview; error?: string; saving?: boolean }
  | { name: "saved"; saved: GeneratedSaved }
  | { name: "failed"; error: string };

function titleOf(markdown: string, subject: string | null, topic: number | null): string {
  const heading = /^#\s+(.+)$/m.exec(markdown)?.[1]?.trim();
  if (heading) return heading;
  return topic !== null && subject ? `Apuntes del tema ${topic} de ${subject}` : "Apuntes";
}

/**
 * «Guardar como nota»: enseña dónde se guardaría y qué se escribiría, y solo escribe (un fichero
 * nuevo en `_generadas/`, sin sobrescribir nada) cuando el usuario confirma.
 */
export function SaveNote({ markdown, subject, topic, sources }: Props) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-border-strong px-3 py-1.5 text-sm hover:bg-surface-2"
      >
        Guardar como nota
      </button>
      {open ? (
        <Dialog
          markdown={markdown}
          subject={subject}
          topic={topic}
          sources={sources}
          onClose={() => {
            setOpen(false);
            queueMicrotask(() => trigger.current?.focus());
          }}
        />
      ) : null}
    </>
  );
}

function Dialog({ markdown, subject, topic, sources, onClose }: Props & { onClose: () => void }) {
  const id = useId();
  const [stage, setStage] = useState<Stage>({ name: "loading" });
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    previewGenerated(
      {
        title: titleOf(markdown, subject, topic),
        markdown,
        asignatura: subject,
        tema: topic,
        sources,
      },
      { signal: controller.signal },
    )
      .then((preview) => !controller.signal.aborted && setStage({ name: "ready", preview }))
      .catch((error: Error) => !controller.signal.aborted && setStage({ name: "failed", error: error.message }));
    return () => controller.abort();
  }, [markdown, subject, topic, sources]);

  async function confirm(preview: GeneratedPreview) {
    setStage({ name: "ready", preview, saving: true });
    try {
      const saved = await saveGenerated({ path: preview.path, content: preview.content });
      setStage({ name: "saved", saved });
    } catch (error) {
      setStage({ name: "ready", preview, error: (error as Error).message });
    }
  }

  // En el `body`: el texto de la respuesta está en un contenedor animado que ataría el «fixed» a él.
  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div aria-hidden="true" className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-titulo`}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          }
        }}
        className="relative flex max-h-[85dvh] w-full max-w-2xl flex-col gap-3 rounded-2xl border border-border bg-surface p-5 shadow-2xl"
      >
        <h2 id={`${id}-titulo`} className="text-lg font-semibold">
          Guardar como nota
        </h2>

        {stage.name === "loading" ? (
          <p role="status" className="text-sm text-muted">
            Preparando la vista previa…
          </p>
        ) : null}

        {stage.name === "failed" ? (
          <p role="alert" className="rounded-lg bg-caution-bg px-3 py-2 text-sm text-caution-fg">
            {stage.error}
          </p>
        ) : null}

        {stage.name === "ready" ? (
          <>
            <p className="text-sm text-muted">
              Se creará esta nota nueva en tu vault (no se sobrescribe nada; si el nombre existe se
              añade un número):
            </p>
            <p className="break-all rounded-lg bg-surface-2 px-3 py-2 font-mono text-sm">{stage.preview.path}</p>
            <pre
              tabIndex={0}
              aria-label="Contenido que se guardará"
              className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-bg p-3 text-xs"
            >
              {stage.preview.content}
            </pre>
            {stage.error ? (
              <p role="alert" className="rounded-lg bg-caution-bg px-3 py-2 text-sm text-caution-fg">
                {stage.error}
              </p>
            ) : null}
          </>
        ) : null}

        {stage.name === "saved" ? (
          <div className="space-y-3">
            <p role="status" className="text-sm">
              Guardado en {stage.saved.path}
            </p>
            <a
              href={stage.saved.obsidian_url}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong px-3 py-1.5 text-sm hover:bg-surface-2"
            >
              <ExternalIcon size={14} />
              Abrir en Obsidian
            </a>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          {stage.name === "ready" ? (
            <button
              type="button"
              disabled={stage.saving}
              onClick={() => void confirm(stage.preview)}
              className="rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-accent-fg disabled:opacity-60"
            >
              Guardar
            </button>
          ) : null}
          <button
            ref={cancel}
            type="button"
            onClick={onClose}
            autoFocus
            className="rounded-lg border border-border-strong px-3.5 py-1.5 text-sm hover:bg-surface-2"
          >
            {stage.name === "saved" ? "Cerrar" : "Cancelar"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
