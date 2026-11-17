import { useId, useState } from "react";

import type { DoneEvent, SourceInfo } from "../lib/api";
import { formatDuration, formatNumber } from "../lib/format";
import { describeNotices } from "../lib/notices";
import { AlertIcon, ChevronIcon, InfoIcon } from "./icons";

interface Props {
  done: DoneEvent;
  sources: SourceInfo[];
  /** Códigos que no se muestran (p. ej. la tarjeta «no lo encuentro» ya explica la confianza). */
  hide?: string[];
}

const TONE = {
  neutral: "border-border bg-surface-2 text-text",
  caution: "border-caution-border bg-caution-bg text-caution-fg",
} as const;

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * Avisos de la respuesta en una línea, sin alarmismo (ni `role="alert"` ni rojo), y un panel
 * plegable con cómo se ha respondido: fuentes, tiempos y tokens.
 */
export function NoticeBar({ done, sources, hide = [] }: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const notices = describeNotices(done).filter((n) => !hide.includes(n.code));
  const visible = notices.filter((n) => !n.detailsOnly);
  const evidence = sources.filter((s) => s.kind === "evidence").length;
  const hints = sources.length - evidence;
  const { timings } = done;

  return (
    <section aria-label="Avisos de la respuesta" className="mt-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {visible.map((notice) => (
          <span
            key={notice.code}
            data-testid="notice"
            data-tone={notice.tone}
            data-code={notice.code}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${TONE[notice.tone]}`}
          >
            {notice.tone === "caution" ? <AlertIcon size={14} /> : <InfoIcon size={14} />}
            {notice.title}
          </span>
        ))}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-muted hover:text-text"
        >
          Cómo se ha respondido
          <ChevronIcon size={14} className={open ? "rotate-180" : undefined} />
        </button>
      </div>

      {open ? (
        <div
          id={panelId}
          role="region"
          aria-label="Cómo se ha respondido"
          className="mt-2 space-y-3 rounded-md border border-border bg-surface p-4"
        >
          {notices.length > 0 ? (
            <ul className="space-y-1">
              {notices.map((notice) => (
                <li key={notice.code}>
                  <strong className="font-semibold">{notice.title}.</strong> {notice.detail}
                </li>
              ))}
            </ul>
          ) : null}
          <p>
            Fuentes consultadas: {plural(evidence, "nota de evidencia", "notas de evidencia")}
            {hints > 0 ? ` y ${plural(hints, "relacionada", "relacionadas")}` : ""}.
          </p>
          <ul className="grid grid-cols-1 gap-x-6 gap-y-1 text-muted sm:grid-cols-2">
            <li>
              Recuperación: <strong className="text-text">{formatDuration(timings.retrieval_ms)}</strong>
            </li>
            <li>
              Primer token: <strong className="text-text">{formatDuration(timings.first_token_ms)}</strong>
            </li>
            <li>
              Total: <strong className="text-text">{formatDuration(timings.total_ms)}</strong>
            </li>
            <li>
              Velocidad:{" "}
              <strong className="text-text">
                {timings.tokens_per_second === null ? "—" : `${Math.round(timings.tokens_per_second)} tok/s`}
              </strong>
            </li>
            <li>
              Tokens:{" "}
              <strong className="text-text">
                {done.prompt_tokens === null ? "—" : formatNumber(done.prompt_tokens)}
              </strong>{" "}
              de entrada ·{" "}
              <strong className="text-text">
                {done.completion_tokens === null ? "—" : formatNumber(done.completion_tokens)}
              </strong>{" "}
              de salida
            </li>
          </ul>
        </div>
      ) : null}
    </section>
  );
}
