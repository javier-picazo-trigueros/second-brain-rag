import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Estado } from "./pages/Estado";
import { Preguntar } from "./pages/Preguntar";

/** El enrutador (BrowserRouter o MemoryRouter) lo pone quien monta la aplicación. */
export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Preguntar />} />
        <Route path="estado" element={<Estado />} />
        <Route path="*" element={<Preguntar />} />
      </Route>
    </Routes>
  );
}
