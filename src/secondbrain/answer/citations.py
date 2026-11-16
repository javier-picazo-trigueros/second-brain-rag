from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from secondbrain.answer.context import Fragment

# El modelo cita con identificadores cortos: [S3], [S1, S4], [S1; S2], [S1 y S2].
_INNER = re.compile(r"\s*S\s?\d{1,3}\s*(?:(?:[,;]|\by\b)\s*S\s?\d{1,3}\s*)*", re.I)
_ID = re.compile(r"S\s?(\d{1,3})", re.I)
# La página la pone el sistema (la del fragmento): la que el modelo añada se descarta.
_PAGE_GROUP = re.compile(r"\((?:pp?|p[áa]gs?)\.?\s*[\d\s,;\-–y]+\)", re.I)
_MAX_RAW = 200  # una cita [[...]] más larga que esto no se considera cita
_MAX_ID_GROUP = 40  # un corchete más largo que esto no es un grupo de identificadores
_MAX_PAGE_GAP = 2  # espacios admitidos entre la cita y su paréntesis de página
_MAX_PAGE_GROUP = 40


@dataclass(slots=True)
class CitationReport:
    citations: list[Fragment] = field(default_factory=list)  # válidas, sin repetir, en orden
    invalid: list[str] = field(default_factory=list)  # identificadores o títulos no verificados

    @property
    def only_hints(self) -> bool:
        return bool(self.citations) and all(c.kind == "hint" for c in self.citations)


class CitationStream:
    """Filtro incremental: deja pasar el texto del modelo verificando cada cita `[S#]`.

    Retiene solo lo imprescindible (desde un posible `[` hasta su `]`, y un posible `(p. N)` justo
    después) para que el cliente no llegue a ver nunca un identificador que no esté en el contexto.
    """

    def __init__(self, fragments: Sequence[Fragment]) -> None:
        self._by_id = {f.id.upper(): f for f in fragments}
        self._pending = ""
        self.report = CitationReport()

    def feed(self, delta: str) -> str:
        self._pending += delta
        return self._drain(final=False)

    def finish(self) -> str:
        return self._drain(final=True)

    # --- resolución ---------------------------------------------------------------------------

    def _cite(self, inner: str) -> str:
        """Texto que sustituye a un corchete de identificadores, registrándolos en el informe."""
        out: list[str] = []
        for match in _ID.finditer(inner):
            fid = f"S{int(match.group(1))}"
            fragment = self._by_id.get(fid)
            if fragment is None:
                self.report.invalid.append(fid)
                out.append(f"[cita no verificada: {fid}]")
                continue
            if all(c.id != fragment.id for c in self.report.citations):
                self.report.citations.append(fragment)
            out.append(f"[{fragment.id}]")
        return "".join(out)

    def _mark_title(self, raw: str) -> str:
        label = raw.strip()
        self.report.invalid.append(label)
        return f"[cita no verificada: {label}]" if label else "[cita no verificada]"

    @staticmethod
    def _could_become_ids(text: str) -> bool:
        """¿Lo que sigue a un `[` aún puede acabar siendo `S<n>...]`? (para esperar más texto)"""
        body = text.lstrip(" ")
        if body == "":
            return True
        return re.match(r"S(\s?\d{0,3}\s*([,;]|\by?\b)?.*)?$", body, re.I) is not None

    def _page_suffix(self, rest: str, *, final: bool) -> int | None:
        """Caracteres a descartar tras una cita (su «(p. N)»); None si falta texto para decidir."""
        gap = len(rest) - len(rest.lstrip(" \t"))
        tail = rest[gap:]
        if gap > _MAX_PAGE_GAP:
            return 0
        if tail == "":
            return 0 if final else None
        if not tail.startswith("("):
            return 0
        close = tail.find(")")
        if close == -1:
            return 0 if final or len(tail) > _MAX_PAGE_GROUP else None
        if _PAGE_GROUP.fullmatch(tail[: close + 1]):
            return gap + close + 1
        return 0

    # --- máquina de estados -------------------------------------------------------------------

    def _drain(self, *, final: bool) -> str:
        out: list[str] = []
        while self._pending:
            start = self._pending.find("[")
            if start == -1:
                out.append(self._pending)
                self._pending = ""
                break
            out.append(self._pending[:start])
            self._pending = self._pending[start:]
            step = self._step(final=final)
            if step is None:
                break
            text, consumed = step
            out.append(text)
            self._pending = self._pending[consumed:]
        return "".join(out)

    def _step(self, *, final: bool) -> tuple[str, int] | None:
        """Resuelve el `[` con el que empieza el buffer. None = esperar más texto."""
        pending = self._pending
        if pending.startswith("[["):
            return self._double(final=final)
        close = pending.find("]")
        newline = pending.find("\n")
        if close == -1:
            if (
                newline != -1
                or len(pending) > _MAX_ID_GROUP
                or not self._could_become_ids(pending[1:])
            ):
                return "[", 1
            return ("[", 1) if final else None
        inner = pending[1:close]
        if (newline != -1 and newline < close) or not _INNER.fullmatch(inner):
            return "[", 1
        suffix = self._page_suffix(pending[close + 1 :], final=final)
        if suffix is None:
            return None
        return self._cite(inner), close + 1 + suffix

    def _double(self, *, final: bool) -> tuple[str, int] | None:
        """`[[Título]]`: ya no es el formato de cita; se marca como no verificada."""
        pending = self._pending
        close = pending.find("]]")
        newline = pending.find("\n", 2)
        if (newline != -1 and (close == -1 or newline < close)) or (
            close == -1 and len(pending) > _MAX_RAW + 3
        ):
            return "[[", 2
        if close == -1:
            return ("[[", 2) if final else None
        inner = pending[2:close]
        consumed = close + 2
        if inner.count("[") > inner.count("]") and pending[consumed : consumed + 1] == "]":
            inner += "]"  # título con corchetes propios: «[[Tema 5 [MD]]]»
            consumed += 1
        if close - 2 > _MAX_RAW:
            return "[[", 2
        return self._mark_title(inner), consumed


def validate_citations(text: str, fragments: Sequence[Fragment]) -> tuple[str, CitationReport]:
    """Versión no incremental: el texto con las citas verificadas y el informe."""
    stream = CitationStream(fragments)
    cleaned = stream.feed(text) + stream.finish()
    return cleaned, stream.report
