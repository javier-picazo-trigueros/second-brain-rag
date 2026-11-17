import { useCallback, useEffect, useState, type ReactNode } from "react";

import { ErrorBanner, extractCommand } from "../components/ErrorBanner";
import { CheckIcon, CopyIcon, RefreshIcon, XIcon } from "../components/icons";
import { useSession } from "../hooks/session";
import {
  ApiError,
  apiGet,
  apiPost,
  type HealthReport,
  type ReindexStatus,
  type Stats,
} from "../lib/api";
import { formatDuration, formatMemory, formatNumber, median, relativeTime } from "../lib/format";

const POLL_MS = 1500;

function Card({ title, ok, children }: { title: string; ok: boolean | null; children: ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-surface p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        {ok === null ? null : (
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm ${
              ok ? "border-border bg-surface-2 text-text" : "border-danger-border bg-danger-bg text-danger-fg"
            }`}
          >
            {ok ? <CheckIcon size={13} /> : <XIcon size={13} />}
            {ok ? "Funciona" : "No funciona"}
          </span>
        )}
      </div>
      <div className="space-y-1 text-sm text-muted">{children}</div>
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm text-muted">{label}</div>
    </div>
  );
}

function Hint({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const command = extractCommand(text);
  async function copy() {
    if (!command) return;
    try {
      await navigator.clipboard?.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // el comando sigue visible en el texto
    }
  }
  return (
    <li className="flex flex-wrap items-center gap-2">
      <span>{text}</span>
      {command ? (
        <button
          type="button"
          onClick={copy}
          aria-label={`Copiar el comando: ${command}`}
          className="inline-flex items-center gap-1 rounded-md border border-border-strong px-2 py-0.5 text-sm hover:bg-surface-2"
        >
          {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
          {copied ? "Copiado" : "Copiar"}
        </button>
      ) : null}
    </li>
  );
}

function reindexSummary(status: ReindexStatus): string | null {
  const r = status.report;
  if (status.state !== "done" || !r) return null;
  const parts = [
    `${formatNumber(r.indexed)} indexadas`,
    `${formatNumber(r.unchanged)} sin cambios`,
    `${formatNumber(r.empty)} vacías`,
    `${formatNumber(r.deleted)} borradas`,
  ];
  if (r.failed.length > 0) parts.push(`${r.failed.length} con error`);
  return parts.join(" · ");
}

export function Estado() {
  const { entries } = useSession();
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [reindex, setReindex] = useState<ReindexStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reindexError, setReindexError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadStats = useCallback(() => {
    apiGet<Stats>("/stats")
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([apiGet<HealthReport>("/health"), apiGet<Stats>("/stats"), apiGet<ReindexStatus>("/reindex/status")])
      .then(([h, s, r]) => {
        if (cancelled) return;
        setHealth(h);
        setStats(s);
        setReindex(r);
        setLoading(false);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setLoadError(error.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const running = reindex?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      apiGet<ReindexStatus>("/reindex/status")
        .then((next) => {
          setReindex(next);
          if (next.state !== "running") loadStats();
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running, loadStats]);

  async function startReindex() {
    setReindexError(null);
    try {
      setReindex(await apiPost<ReindexStatus>("/reindex", undefined));
    } catch (error) {
      setReindexError(error instanceof ApiError || error instanceof Error ? error.message : String(error));
    }
  }

  const totals = entries.map((entry) => entry.timings.total_ms);
  const typical = median(totals);
  const summary = reindex ? reindexSummary(reindex) : null;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6">
      <h1 className="text-2xl font-semibold">Estado</h1>

      {loading ? (
        <p role="status" className="text-muted">
          Comprobando servicios…
        </p>
      ) : null}
      {loadError ? <ErrorBanner message={loadError} /> : null}

      {health ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Card title="Ollama" ok={health.ollama.ok}>
              {health.ollama.ok ? (
                <>
                  <p>{health.ollama.version ? `versión ${health.ollama.version}` : "en marcha"}</p>
                  <ul>
                    {Object.entries(health.ollama.models).map(([name, present]) => (
                      <li key={name}>
                        {name}: {present ? "instalado" : "falta"}
                      </li>
                    ))}
                  </ul>
                  {health.ollama.loaded.length > 0 ? (
                    <p>En memoria: {health.ollama.loaded.map((m) => `${m.name} (${formatMemory(m.vram_mib)})`).join(", ")}</p>
                  ) : null}
                </>
              ) : (
                <p>{health.ollama.error ?? "No responde"}</p>
              )}
            </Card>
            <Card title="Qdrant" ok={health.qdrant.ok}>
              {health.qdrant.ok ? (
                <p>{health.qdrant.points === null ? "en marcha" : `${formatNumber(health.qdrant.points)} puntos`}</p>
              ) : (
                <p>{health.qdrant.error ?? "No responde"}</p>
              )}
            </Card>
            <Card title="Vault" ok={health.vault.ok}>
              <p className="break-all">{health.vault.path}</p>
              {health.vault.ok ? null : <p>No se encuentra la carpeta.</p>}
            </Card>
          </div>

          {health.gpu ? (
            <section className="rounded-md border border-border bg-surface p-4">
              <h2 className="mb-2 text-lg font-semibold">Memoria de la GPU</h2>
              <progress
                aria-label="Memoria de la GPU"
                aria-valuenow={health.gpu.used_mib}
                aria-valuemin={0}
                aria-valuemax={health.gpu.total_mib}
                aria-valuetext={`${formatMemory(health.gpu.used_mib)} de ${formatMemory(health.gpu.total_mib)}`}
                value={health.gpu.used_mib}
                max={health.gpu.total_mib}
                className="h-3 w-full overflow-hidden rounded-full accent-[var(--accent)]"
              />
              <p className="mt-1 text-sm text-muted">
                {formatMemory(health.gpu.used_mib)} de {formatMemory(health.gpu.total_mib)} en uso
              </p>
            </section>
          ) : null}

          {health.hints.length > 0 ? (
            <section aria-label="Qué hacer" className="rounded-md border border-border bg-surface-2 p-4">
              <h2 className="mb-2 text-lg font-semibold">Qué hacer</h2>
              <ul className="space-y-2 text-sm">
                {health.hints.map((hint) => (
                  <Hint key={hint} text={hint} />
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}

      {stats ? (
        <section aria-label="Índice" className="space-y-3">
          <h2 className="text-lg font-semibold">Índice</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Figure label="notas" value={formatNumber(stats.notes)} />
            <Figure label="fragmentos" value={formatNumber(stats.chunks)} />
            <Figure label="conceptos" value={formatNumber(stats.concepts)} />
            <Figure label="grupos duplicados" value={formatNumber(stats.duplicate_groups)} />
          </div>
          <p className="text-sm text-muted">Última sincronización: {relativeTime(stats.last_sync)}</p>
        </section>
      ) : null}

      {reindex ? (
        <section aria-label="Reindexado" className="rounded-md border border-border bg-surface p-4">
          <h2 className="mb-2 text-lg font-semibold">Reindexado</h2>
          <button
            type="button"
            onClick={startReindex}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshIcon size={14} />
            {running ? "Reindexando…" : "Reindexar ahora"}
          </button>
          {running ? (
            <div className="mt-3">
              <progress
                aria-label="Progreso del reindexado"
                aria-valuenow={reindex.done}
                aria-valuemin={0}
                aria-valuemax={reindex.total}
                value={reindex.done}
                max={Math.max(reindex.total, 1)}
                className="h-3 w-full accent-[var(--accent)]"
              />
              <p className="mt-1 text-sm text-muted">
                {formatNumber(reindex.done)} de {formatNumber(reindex.total)} notas
              </p>
            </div>
          ) : null}
          {summary ? <p className="mt-3 text-sm text-muted">{summary}</p> : null}
          {reindex.state === "error" && reindex.error ? <div className="mt-3"><ErrorBanner message={reindex.error} /></div> : null}
          {reindexError ? <p className="mt-3 text-sm text-muted">{reindexError}</p> : null}
        </section>
      ) : null}

      <section aria-label="Latencia" className="rounded-md border border-border bg-surface p-4">
        <h2 className="mb-1 text-lg font-semibold">Latencia de esta sesión</h2>
        {typical === null ? (
          <p className="text-sm text-muted">Aún no hay respuestas en esta sesión.</p>
        ) : (
          <p className="text-sm text-muted">
            Tiempo típico de respuesta: <strong className="text-lg text-text">{formatDuration(typical)}</strong>{" "}
            <span>(mediana de {entries.length} {entries.length === 1 ? "respuesta" : "respuestas"})</span>
          </p>
        )}
      </section>
    </div>
  );
}
