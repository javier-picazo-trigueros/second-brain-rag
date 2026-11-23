import type { DoneEvent } from "./api";

export type NoticeTone = "neutral" | "caution";

export interface Notice {
  code: string;
  tone: NoticeTone;
  title: string;
  detail: string;
  /** Solo se muestra dentro de «Cómo se ha respondido» (si no, sería ruido constante). */
  detailsOnly?: boolean;
}

const ORDER = [
  "respuesta_contradictoria",
  "respuesta_parcial",
  "numeros_no_verificados",
  "pasos_sin_cita",
  "citas_no_verificadas",
  "sin_citas",
  "solo_pistas",
  "respuesta_truncada",
  "parte_sin_terminar",
  "pregunta_recortada",
  "confianza_baja",
  "contexto_recortado",
];

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function decimal(value: number): string {
  return value.toFixed(2).replace(".", ",");
}

function build(code: string, done: DoneEvent): Notice | null {
  switch (code) {
    case "pregunta_recortada":
      return { code, tone: "neutral", title: "Pregunta recortada", detail: "Se ha usado el inicio de la pregunta hasta el límite permitido." };
    case "confianza_baja":
      return {
        code,
        tone: "neutral",
        title: "Relevancia de las fuentes baja",
        detail:
          "Tu pregunta se parece poco a lo que hay en tus apuntes" +
          (done.similarity === null ? "" : ` (similitud ${decimal(done.similarity)})`) +
          ". Contrasta la respuesta con las fuentes.",
      };
    case "citas_no_verificadas": {
      const n = Math.max(done.invalid.length, 1);
      return {
        code,
        tone: "caution",
        title: plural(n, "cita no verificada", "citas no verificadas"),
        detail:
          "El modelo nombró notas que no estaban entre las fuentes consultadas. " +
          "En el texto aparecen marcadas con «?».",
      };
    }
    case "respuesta_contradictoria":
      return {
        code,
        tone: "caution",
        title: "Respuesta descartada",
        detail:
          "El modelo escribió contenido y después dijo que no lo encuentra en tus apuntes; " +
          "se ha descartado lo escrito porque no es de fiar.",
      };
    case "respuesta_parcial":
      return {
        code,
        tone: "caution",
        title: "Respuesta parcial",
        detail:
          "El modelo no encontró parte de lo que preguntas. Solo se conservan las frases con cita " +
          "verificada; el resto se ha descartado.",
      };
    case "numeros_no_verificados": {
      const numbers = done.unverified_numbers ?? [];
      return {
        code,
        tone: "caution",
        title: `${numbers.length} ${numbers.length === 1 ? "número sin verificar" : "números sin verificar"}`,
        detail:
          `No aparecen en las fuentes: ${numbers.join(", ")}. El modelo debe copiar los resultados ` +
          "de la solución, no recalcularlos: compruébalos antes de fiarte.",
      };
    }
    case "pasos_sin_cita": {
      const steps = done.uncited_steps ?? 0;
      return {
        code,
        tone: "caution",
        title: `${steps} ${steps === 1 ? "paso sin cita" : "pasos sin cita"}`,
        detail: "Algún paso no indica de qué nota sale, así que no se puede comprobar.",
      };
    }
    case "sin_citas":
      return {
        code,
        tone: "caution",
        title: "Respuesta sin citas",
        detail: "No cita ninguna nota, así que no se puede comprobar de dónde sale. Úsala con cuidado.",
      };
    case "solo_pistas":
      return {
        code,
        tone: "caution",
        title: "Solo cita notas relacionadas",
        detail: "Las notas relacionadas son pistas automáticas, no evidencia.",
      };
    case "respuesta_truncada":
      return {
        code,
        tone: "caution",
        title: "Respuesta cortada",
        detail: "Se alcanzó el límite de longitud. Prueba con una pregunta más concreta.",
      };
    case "parte_sin_terminar":
      return {
        code,
        tone: "caution",
        title: "Apuntes con una parte sin terminar",
        detail:
          "Alguna parte llegó al límite de longitud y no se pudo continuar. Lo escrito se conserva; " +
          "puedes volver a pedir ese apartado con una pregunta más concreta.",
      };
    case "contexto_recortado":
      return {
        code,
        tone: "neutral",
        title: "Contexto recortado",
        detail: "Algunas fuentes se han acortado para caber en la memoria del modelo.",
        detailsOnly: true,
      };
    default:
      return null;
  }
}

export function describeNotices(done: DoneEvent): Notice[] {
  return ORDER.filter((code) => done.warnings.includes(code))
    .map((code) => build(code, done))
    .filter((notice): notice is Notice => notice !== null);
}

/** Una línea con los avisos visibles: «1 cita no verificada · Relevancia de las fuentes baja». */
export function summarizeNotices(notices: Notice[]): string {
  return notices
    .filter((n) => !n.detailsOnly)
    .map((n) => n.title)
    .join(" · ");
}
