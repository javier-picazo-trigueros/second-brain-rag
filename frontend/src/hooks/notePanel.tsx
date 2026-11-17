import { createContext, useContext } from "react";

export interface NoteApi {
  open: (path: string, page: number | null) => void;
  close: () => void;
}

export const NoteContext = createContext<NoteApi>({ open: () => {}, close: () => {} });

export function useNotePanel(): NoteApi {
  return useContext(NoteContext);
}
