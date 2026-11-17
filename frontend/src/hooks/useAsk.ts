import { useCallback, useReducer, useRef } from "react";

import { askStream } from "../lib/api";
import { askReducer, initialAskState } from "./askState";

const INTERRUPTED = "Conexión interrumpida: la respuesta quedó incompleta. Vuelve a preguntar.";

export function useAsk() {
  const [state, dispatch] = useReducer(askReducer, initialAskState);
  const controller = useRef<AbortController | null>(null);

  const ask = useCallback(async (question: string) => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    dispatch({ type: "start", question });
    let finished = false;
    try {
      for await (const event of askStream(question, { signal: mine.signal })) {
        if (event.type === "done" || event.type === "error") finished = true;
        dispatch(event);
      }
      if (!finished && !mine.signal.aborted) dispatch({ type: "failed", message: INTERRUPTED });
    } catch (error) {
      if (mine.signal.aborted) return;
      dispatch({ type: "failed", message: error instanceof Error ? error.message : String(error) });
    }
  }, []);

  const stop = useCallback(() => {
    controller.current?.abort();
    dispatch({ type: "stop" });
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    dispatch({ type: "reset" });
  }, []);

  return { state, ask, stop, reset };
}
