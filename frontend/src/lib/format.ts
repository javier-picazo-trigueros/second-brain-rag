const numberFormat = new Intl.NumberFormat("es-ES", { useGrouping: "always" });

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

function oneDecimal(value: number): string {
  return value.toFixed(1).replace(".", ",");
}

/** 420 ms, 2,3 s, 12 s, 1 min 5 s. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 9.95) return `${oneDecimal(seconds)} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`;
}

/** 512 MiB, 4,8 GiB. */
export function formatMemory(mib: number): string {
  return mib >= 1024 ? `${oneDecimal(mib / 1024)} GiB` : `${Math.round(mib)} MiB`;
}

/** "hace 5 min", "ayer"... Una fecha futura cercana (reloj desfasado) cuenta como "ahora". */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "nunca";
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "hace unos segundos";
  if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
  if (seconds < 86_400) return `hace ${Math.floor(seconds / 3600)} h`;
  if (seconds < 172_800) return "ayer";
  return `hace ${Math.floor(seconds / 86_400)} días`;
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}
