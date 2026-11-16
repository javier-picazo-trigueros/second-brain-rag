import { useState } from "react";

import { AlertIcon, CheckIcon, CopyIcon } from "./icons";

/** Primer fragmento entre comillas invertidas: el comando que arregla el problema. */
export function extractCommand(message: string): string | null {
  const match = message.match(/`([^`]+)`/);
  return match ? match[1]! : null;
}

interface Props {
  message: string;
}

/** El único aviso en rojo de la interfaz: un servicio caído o una petición fallida. */
export function ErrorBanner({ message }: Props) {
  const [copied, setCopied] = useState(false);
  const command = extractCommand(message);

  async function copy() {
    if (!command) return;
    try {
      await navigator.clipboard?.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // sin permiso de portapapeles: el comando sigue visible en el mensaje
    }
  }

  return (
    <div
      role="alert"
      className="flex flex-wrap items-start gap-3 rounded-md border border-danger-border bg-danger-bg p-4 text-danger-fg"
    >
      <AlertIcon size={20} className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1">{message}</p>
      {command ? (
        <button
          type="button"
          onClick={copy}
          aria-label={`Copiar el comando: ${command}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-danger-border bg-surface px-3 py-1 text-sm font-medium text-danger-fg hover:bg-surface-2"
        >
          {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
          Copiar
        </button>
      ) : null}
      <span aria-live="polite" className="text-sm">
        {copied ? "Copiado" : ""}
      </span>
    </div>
  );
}
