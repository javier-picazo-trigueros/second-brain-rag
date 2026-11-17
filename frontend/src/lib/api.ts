import { parseSse } from "./sse";

// --- tipos que expone la API de Python (ver src/secondbrain/api/schemas.py) ---------------------

export interface LoadedModel {
  name: string;
  vram_mib: number;
  expires_at: string | null;
}

export interface HealthReport {
  status: "ok" | "degraded" | "down";
  ollama: {
    ok: boolean;
    version: string | null;
    models: Record<string, boolean>;
    loaded: LoadedModel[];
    error: string | null;
  };
  qdrant: { ok: boolean; points: number | null; error: string | null };
  vault: { ok: boolean; path: string };
  gpu: { used_mib: number; total_mib: number } | null;
  hints: string[];
}

export interface Stats {
  notes: number;
  chunks: number;
  points: number;
  duplicate_groups: number;
  concepts: number;
  last_sync: string | null;
}

export interface ReindexReport {
  indexed: number;
  unchanged: number;
  empty: number;
  deleted: number;
  failed: { path: string; error: string }[];
}

export interface ReindexStatus {
  state: "idle" | "running" | "done" | "error";
  done: number;
  total: number;
  current: string | null;
  started_at: string | null;
  finished_at: string | null;
  report: ReindexReport | null;
  error: string | null;
}

export interface Neighbor {
  path: string;
  title: string;
  score: number;
  via: string[];
}

export interface NoteDetail {
  path: string;
  title: string;
  asignatura: string | null;
  curso: string | null;
  frontmatter: Record<string, unknown>;
  tags: string[];
  concepts: string[];
  links: string[];
  body: string;
  related: Neighbor[];
}

// --- eventos de /ask ------------------------------------------------------------------------

export interface SourceInfo {
  label: string;
  path: string;
  title: string;
  kind: "evidence" | "hint";
  pages: number[];
  asignatura: string | null;
  curso: string | null;
  truncated: boolean;
}

/** Un trozo citable del contexto: el modelo lo cita con su `id` (p. ej. «S3»). */
export interface FragmentInfo {
  id: string;
  label: string;
  path: string;
  title: string;
  kind: "evidence" | "hint";
  page: number | null;
  heading: string | null;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface Facets {
  asignaturas: FacetValue[];
  cursos: FacetValue[];
  tags: FacetValue[];
}

export interface SearchChunk {
  heading_path: string;
  page: number | null;
  text: string;
  score: number;
}

export interface SearchNote {
  path: string;
  title: string;
  score: number;
  n_chunks: number;
  asignatura: string | null;
  curso: string | null;
  tags: string[];
  also_in: string[];
  chunks: SearchChunk[];
}

export interface SearchResponse {
  notes: SearchNote[];
  top_similarity: number | null;
  confidence: string;
  facets: Facets;
}

export interface SubjectInfo {
  name: string;
  notes: number;
}

export interface Timings {
  retrieval_ms: number;
  first_token_ms: number | null;
  total_ms: number;
  llm_load_ms: number | null;
  tokens_per_second: number | null;
}

export type Confidence = "alta" | "baja" | "desconocida";

export interface SourcesEvent {
  type: "sources";
  sources: SourceInfo[];
  fragments: FragmentInfo[];
  confidence: Confidence;
  similarity: number | null;
  dropped_notes: number;
}

export interface TokenEvent {
  type: "token";
  text: string;
}

export interface DoneEvent {
  type: "done";
  answer: string;
  citations: FragmentInfo[];
  invalid: string[];
  warnings: string[];
  not_found: boolean;
  confidence: Confidence;
  similarity: number | null;
  timings: Timings;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export type AskEvent = SourcesEvent | TokenEvent | DoneEvent | ErrorEvent;

// --- cliente HTTP ---------------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const UNREACHABLE =
  "No se puede conectar con la API. ¿Está arrancada? Ejecuta `brain serve` (o `.\\tasks.ps1 serve`).";

export interface RequestOptions {
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

async function errorFrom(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return new ApiError(response.status, detail);
    if (Array.isArray(detail)) {
      const messages = detail.map((d: { msg?: string }) => d.msg ?? "valor no válido");
      return new ApiError(response.status, messages.join("; "));
    }
  } catch {
    // el cuerpo no era JSON: se usa el texto de estado
  }
  return new ApiError(response.status, `Error ${response.status}: ${response.statusText || "sin detalle"}`);
}

async function request(
  method: "GET" | "POST",
  path: string,
  body: unknown,
  { fetchImpl = fetch, signal }: RequestOptions,
  extraHeaders: Record<string, string> = {},
): Promise<Response> {
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method,
      signal,
      headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...extraHeaders },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await (await request("GET", path, undefined, options)).json()) as T;
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  return (await (await request("POST", path, body, options)).json()) as T;
}

/** Pregunta al modelo y entrega los eventos SSE ya tipados a medida que llegan. */
export async function* askStream(
  question: string,
  options: RequestOptions & { k?: number } = {},
): AsyncGenerator<AskEvent> {
  const { k, ...rest } = options;
  const body = k === undefined ? { question } : { question, k };
  const response = await request("POST", "/ask", body, rest, { Accept: "text/event-stream" });
  if (!response.body) {
    yield { type: "error", message: "La API no devolvió ningún contenido." };
    return;
  }
  for await (const message of parseSse(response.body)) {
    let payload: unknown;
    try {
      payload = JSON.parse(message.data);
    } catch {
      yield { type: "error", message: "La respuesta del servidor llegó ilegible." };
      return;
    }
    switch (message.event) {
      case "sources":
      case "token":
      case "done":
      case "error":
        yield { type: message.event, ...(payload as object) } as AskEvent;
        break;
      default:
        break; // eventos futuros que esta versión no conoce
    }
  }
}
