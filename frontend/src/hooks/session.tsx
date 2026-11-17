import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { DoneEvent } from "../lib/api";

export interface SessionApi {
  /** Respuestas terminadas en esta sesión del navegador (solo en memoria). */
  entries: DoneEvent[];
  record: (done: DoneEvent) => void;
}

export const SessionContext = createContext<SessionApi>({ entries: [], record: () => {} });

export function useSession(): SessionApi {
  return useContext(SessionContext);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<DoneEvent[]>([]);
  const record = useCallback((done: DoneEvent) => setEntries((prev) => [...prev, done]), []);
  const value = useMemo(() => ({ entries, record }), [entries, record]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
