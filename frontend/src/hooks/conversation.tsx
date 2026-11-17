import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { AskState } from "./askState";
import { useSession } from "./session";
import { useAsk } from "./useAsk";

export interface ConversationApi {
  /** Todas las preguntas de la sesión, de la más antigua a la actual. */
  turns: AskState[];
  busy: boolean;
  ask: (question: string) => void;
  stop: () => void;
}

const ConversationContext = createContext<ConversationApi | null>(null);

/**
 * Vive por encima de las rutas: al ir a Estado y volver, las preguntas y respuestas siguen ahí.
 * Cada pregunta es independiente para el modelo; esto solo conserva lo que se ve en pantalla.
 */
export function ConversationProvider({ children }: { children: ReactNode }) {
  const { state, ask, stop } = useAsk();
  const { record } = useSession();
  const [history, setHistory] = useState<AskState[]>([]);
  const recorded = useRef<unknown>(null);

  useEffect(() => {
    if (state.done && recorded.current !== state.done) {
      recorded.current = state.done;
      record(state.done);
    }
  }, [state.done, record]);

  const submit = useCallback(
    (question: string) => {
      if (state.status !== "idle") setHistory((previous) => [...previous, state]);
      void ask(question);
    },
    [state, ask],
  );

  const value = useMemo<ConversationApi>(
    () => ({
      turns: state.status === "idle" ? history : [...history, state],
      busy: state.status === "waiting" || state.status === "streaming",
      ask: submit,
      stop,
    }),
    [history, state, submit, stop],
  );
  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation(): ConversationApi {
  const value = useContext(ConversationContext);
  if (value === null) throw new Error("useConversation debe usarse dentro de ConversationProvider");
  return value;
}
