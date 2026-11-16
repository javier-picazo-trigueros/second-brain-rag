from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from secondbrain.answer.context import Source

_MAX_RAW = 200  # una cita [[...]] más larga que esto no se considera cita
# "(p. 7)", "(pp. 7, 9)", "(págs. 7 y 9)", "(p. 7-9)": se comprueban todos los números citados.
_PAGE_EXPR = re.compile(
    r"\s*(?:pp?|p[áa]gs?)\.?\s*(?P<nums>\d+(?:\s*(?:[-\u2013,;]|y)\s*\d+)*)\s*", re.I
)
_MAX_PAGE_GAP = 2  # espacios admitidos antes de cada paréntesis posterior a la cita
_MAX_GROUP = 40  # un paréntesis más largo que esto no se considera una anotación
_MAX_GROUPS = 2  # p. ej. "[[Nota]] (EDA, 3º) (p. 7)": una anotación y la página


@dataclass(frozen=True, slots=True)
class Citation:
    label: str
    path: str
    title: str
    kind: str  # "evidence" | "hint"
    page: int | None


@dataclass(slots=True)
class CitationReport:
    citations: list[Citation] = field(default_factory=list)  # válidas, sin repetir, en orden
    invalid: list[str] = field(default_factory=list)  # destinos que no están en el contexto
    bad_pages: list[tuple[str, int]] = field(default_factory=list)  # (ruta, página no verificada)

    @property
    def only_hints(self) -> bool:
        return bool(self.citations) and all(c.kind == "hint" for c in self.citations)


class CitationStream:
    """Filtro incremental: deja pasar el texto del modelo verificando cada [[cita]].

    Retiene solo lo imprescindible (desde un posible `[[` hasta su `]]`, y un posible `(p. N)`
    justo después) para que el cliente no llegue a ver nunca una cita que no esté en el contexto.
    """

    def __init__(self, sources: Sequence[Source]) -> None:
        self._sources = list(sources)
        self._pending = ""
        self.report = CitationReport()

    def feed(self, delta: str) -> str:
        self._pending += delta
        return self._drain(final=False)

    def finish(self) -> str:
        return self._drain(final=True)

    # --- resolución ---------------------------------------------------------------------------

    @staticmethod
    def _target(raw: str) -> str:
        return raw.split("|")[0].split("#")[0].strip()

    def _resolve(self, raw: str) -> Source | None:
        key = self._target(raw).removesuffix(".md").casefold()
        if not key:
            return None
        for matches in (
            [s for s in self._sources if s.label.casefold() == key],
            [s for s in self._sources if s.path.removesuffix(".md").casefold() == key],
            [s for s in self._sources if s.title.casefold() == key],
        ):
            if len(matches) == 1:
                return matches[0]
        return None

    def _add_citation(self, source: Source, page: int | None) -> None:
        citation = Citation(source.label, source.path, source.title, source.kind, page)
        if all((c.path, c.page) != (citation.path, citation.page) for c in self.report.citations):
            self.report.citations.append(citation)

    # --- máquina de estados -------------------------------------------------------------------

    def _drain(self, *, final: bool) -> str:
        out: list[str] = []
        while self._pending:
            start = self._pending.find("[[")
            if start == -1:
                keep = 1 if (not final and self._pending.endswith("[")) else 0
                out.append(self._pending[: len(self._pending) - keep])
                self._pending = self._pending[len(self._pending) - keep :]
                break
            out.append(self._pending[:start])
            self._pending = self._pending[start:]
            close = self._pending.find("]]")
            newline = self._pending.find("\n", 2)
            not_a_citation = (
                (newline != -1 and (close == -1 or newline < close))
                or (close != -1 and close - 2 > _MAX_RAW)
                or (close == -1 and len(self._pending) > _MAX_RAW + 3)
            )
            if not_a_citation:
                out.append("[[")
                self._pending = self._pending[2:]
                continue
            if close == -1:
                if final:
                    out.append(self._pending)
                    self._pending = ""
                break
            raw = self._pending[2:close]
            rest = self._pending[close + 2 :]
            source = self._resolve(raw)
            if source is None:
                self.report.invalid.append(self._target(raw))
                label = self._target(raw)
                out.append(f"[cita no verificada: {label}]" if label else "[cita no verificada]")
                self._pending = rest
                continue
            suffix = self._page_suffix(source, rest, final=final)
            if suffix is None:
                break  # puede venir "(p. N)" en los próximos tokens: se espera
            replacement, consumed = suffix
            out.append(f"[[{source.label}]]{replacement}")
            self._pending = rest[consumed:]
        return "".join(out)

    def _page_suffix(self, source: Source, rest: str, *, final: bool) -> tuple[str, int] | None:
        """Texto que sustituye al sufijo posterior a una cita válida y cuántos caracteres consume.

        El sufijo son hasta `_MAX_GROUPS` paréntesis: las anotaciones (p. ej. "(EDA, 3º)") pasan
        tal cual y la página "(p. N)" se comprueba contra las páginas del contexto. Devuelve None
        si aún no se puede decidir porque pueden faltar tokens.
        """
        position = 0
        kept = ""
        for _ in range(_MAX_GROUPS):
            tail = rest[position:]
            group = tail.lstrip(" \t")
            gap = len(tail) - len(group)
            if gap > _MAX_PAGE_GAP:
                break
            if not group:
                if not final:
                    return None  # puede venir un paréntesis en los próximos tokens
                break
            if not group.startswith("("):
                break
            close = group.find(")")
            if close == -1:
                if not final and len(group) <= _MAX_GROUP + 2:
                    return None  # paréntesis sin cerrar: se espera
                break
            inner = group[1:close]
            if "(" in inner or "\n" in inner or len(inner) > _MAX_GROUP:
                break
            end = position + gap + close + 1
            match = _PAGE_EXPR.fullmatch(inner)
            if match is None:
                kept += rest[position:end]
                position = end
                continue
            return self._check_pages(source, kept, rest[position : position + gap], match, end)
        self._add_citation(source, None)
        return kept, position

    def _check_pages(
        self, source: Source, kept: str, space: str, match: re.Match[str], end: int
    ) -> tuple[str, int]:
        numbers = [int(n) for n in re.findall(r"\d+", match.group("nums"))]
        unknown = [n for n in numbers if n not in source.pages]
        if not unknown:
            self._add_citation(source, numbers[0])
            original = f"{space}({match.string})"
            return kept + original, end
        self.report.bad_pages.extend((source.path, n) for n in unknown)
        self._add_citation(source, None)
        shown = match.group("nums").strip()
        return f"{kept}{space}(p. {shown} no verificada)", end


def validate_citations(text: str, sources: Sequence[Source]) -> tuple[str, CitationReport]:
    """Versión no incremental: el texto con las citas verificadas y el informe."""
    stream = CitationStream(sources)
    cleaned = stream.feed(text) + stream.finish()
    return cleaned, stream.report
