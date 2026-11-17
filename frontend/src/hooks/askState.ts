import type { AskEvent, Confidence, DoneEvent, FragmentInfo, SourceInfo } from "../lib/api";

export type AskStatus = "idle" | "waiting" | "streaming" | "done" | "error" | "stopped";

export interface AskState {
  status: AskStatus;
  question: string;
  /** Texto ya verificado por el servidor: nunca contiene una cita sin comprobar. */
  text: string;
  sources: SourceInfo[];
  /** Cada identificador [S#] que el modelo podía citar. */
  fragments: FragmentInfo[];
  confidence: Confidence | null;
  similarity: number | null;
  droppedNotes: number;
  done: DoneEvent | null;
  error: string | null;
}

export type AskAction =
  | AskEvent
  | { type: "start"; question: string }
  | { type: "stop" }
  | { type: "reset" }
  | { type: "failed"; message: string };

export const initialAskState: AskState = {
  status: "idle",
  question: "",
  text: "",
  sources: [],
  fragments: [],
  confidence: null,
  similarity: null,
  droppedNotes: 0,
  done: null,
  error: null,
};

const LIVE: readonly AskStatus[] = ["waiting", "streaming"];

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "start":
      return { ...initialAskState, status: "waiting", question: action.question };
    case "reset":
      return initialAskState;
    case "stop":
      return LIVE.includes(state.status) ? { ...state, status: "stopped" } : state;
    case "failed":
      return { ...state, status: "error", error: action.message };
    default:
      break;
  }
  // Tras parar (o terminar) se ignoran los eventos rezagados del flujo anterior.
  if (!LIVE.includes(state.status)) return state;
  switch (action.type) {
    case "sources":
      return {
        ...state,
        status: "streaming",
        sources: action.sources,
        fragments: action.fragments,
        confidence: action.confidence,
        similarity: action.similarity,
        droppedNotes: action.dropped_notes,
      };
    case "token":
      return { ...state, status: "streaming", text: state.text + action.text };
    case "done":
      return { ...state, status: "done", text: action.answer, done: action };
    case "error":
      return { ...state, status: "error", error: action.message };
  }
}
