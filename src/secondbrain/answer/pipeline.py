from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Protocol

from secondbrain.answer.citations import CitationStream
from secondbrain.answer.context import BuiltContext, Fragment, Source, build_context
from secondbrain.answer.llm import LLM, Delta, Finished, LLMError
from secondbrain.answer.prompt import NOT_FOUND, build_messages
from secondbrain.config import Settings
from secondbrain.retrieval.hybrid import SearchResult

log = logging.getLogger(__name__)

_EMPTY = BuiltContext("", (), 0, 0, "search", ())


def _contradiction(answer: str) -> bool:
    """¿Hay contenido antes de «No lo encuentro en el vault»? (al principio es legítimo)."""
    at = answer.find(NOT_FOUND)
    return at > 0 and answer[:at].strip() != ""


class Retriever(Protocol):
    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult: ...


@dataclass(frozen=True, slots=True)
class SourcesEvent:
    """Notas recuperadas: lo único que el modelo podrá citar. Se envía antes de generar."""

    sources: tuple[Source, ...]
    fragments: tuple[Fragment, ...]  # cada identificador [S#] que el modelo puede citar
    confidence: str
    similarity: float | None
    dropped_notes: int


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """Texto ya verificado que se puede mostrar al usuario."""

    text: str


@dataclass(frozen=True, slots=True)
class Timings:
    retrieval_ms: float
    first_token_ms: float | None
    total_ms: float
    llm_load_ms: float | None
    tokens_per_second: float | None


@dataclass(frozen=True, slots=True)
class DoneEvent:
    answer: str
    citations: tuple[Fragment, ...]
    invalid: tuple[str, ...]
    warnings: tuple[str, ...]
    not_found: bool
    confidence: str
    similarity: float | None
    timings: Timings
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str


Event = SourcesEvent | TokenEvent | DoneEvent | ErrorEvent


_TOP_NOTES = 3  # solo importa lo que se pierde de las notas más relevantes


def _context_cut_matters(context: BuiltContext) -> bool:
    """¿Se recortó o se dejó fuera algo de las 3 primeras notas? Las demás son relleno."""
    evidence = [s for s in context.sources if s.kind == "evidence"]
    if any(s.truncated for s in evidence[:_TOP_NOTES]):
        return True
    return context.dropped_notes > 0 and len(evidence) < _TOP_NOTES


def confidence_label(similarity: float | None, threshold: float) -> str:
    if similarity is None:
        return "desconocida"
    return "alta" if similarity >= threshold else "baja"


class AnswerPipeline:
    """Recuperar -> contexto -> prompt -> respuesta en streaming con citas verificadas."""

    def __init__(
        self,
        settings: Settings,
        retriever: Retriever,
        llm: LLM,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._s = settings
        self._retriever = retriever
        self._llm = llm
        self._clock = clock

    def plan(self, question: str, k: int | None = None) -> tuple[SearchResult, BuiltContext]:
        """Recuperación y contexto de una pregunta, sin llamar al modelo."""
        result = self._retriever.search(question, k=k or self._s.answer_k, with_graph=True)
        return result, build_context(result, self._s)

    def ask(self, question: str, k: int | None = None) -> Iterator[Event]:
        start = self._clock()
        result, context = self.plan(question, k)
        retrieval_ms = (self._clock() - start) * 1000
        confidence = confidence_label(result.top_similarity, self._s.confidence_threshold)
        yield SourcesEvent(
            context.sources,
            context.fragments,
            confidence,
            result.top_similarity,
            context.dropped_notes,
        )

        if result.canned:
            # Respuesta fija (p. ej. «no hay ejercicios de ese tema»): no pasa por el modelo.
            yield TokenEvent(result.canned)
            timings = Timings(retrieval_ms, None, (self._clock() - start) * 1000, None, None)
            yield DoneEvent(
                answer=result.canned,
                citations=(),
                invalid=(),
                warnings=(),
                not_found=False,
                confidence=confidence,
                similarity=result.top_similarity,
                timings=timings,
                prompt_tokens=None,
                completion_tokens=None,
            )
            return

        if not any(s.kind == "evidence" for s in context.sources):
            # Sin notas recuperadas no hay nada que preguntarle al modelo.
            yield TokenEvent(NOT_FOUND)
            timings = Timings(retrieval_ms, None, (self._clock() - start) * 1000, None, None)
            yield DoneEvent(
                answer=NOT_FOUND,
                citations=(),
                invalid=(),
                warnings=(),
                not_found=True,
                confidence=confidence,
                similarity=result.top_similarity,
                timings=timings,
                prompt_tokens=None,
                completion_tokens=None,
            )
            return

        stream = CitationStream(context.fragments)
        parts: list[str] = []
        first_token_ms: float | None = None
        finished: Finished | None = None
        try:
            for item in self._llm.stream_chat(build_messages(question, context)):
                if isinstance(item, Delta):
                    piece = stream.feed(item.text)
                else:
                    finished = item
                    piece = ""
                if piece:
                    if first_token_ms is None:
                        first_token_ms = (self._clock() - start) * 1000
                    parts.append(piece)
                    yield TokenEvent(piece)
                    if _contradiction("".join(parts)):
                        break  # no se sigue generando: la respuesta se descarta al final
            tail = "" if _contradiction("".join(parts)) else stream.finish()
        except LLMError as exc:
            log.warning("Fallo del modelo: %s", exc)
            yield ErrorEvent(str(exc))
            return
        if tail:
            if first_token_ms is None:
                first_token_ms = (self._clock() - start) * 1000
            parts.append(tail)
            yield TokenEvent(tail)

        answer = "".join(parts)
        if _contradiction(answer):
            yield self._contradictory(
                stream, finished, confidence, result.top_similarity, retrieval_ms,
                first_token_ms, (self._clock() - start) * 1000,
            )  # fmt: skip
            return
        yield self._done(
            "".join(parts), stream, context, finished, confidence, result.top_similarity,
            retrieval_ms, first_token_ms, (self._clock() - start) * 1000,
        )  # fmt: skip

    def _contradictory(
        self,
        stream: CitationStream,
        finished: Finished | None,
        confidence: str,
        similarity: float | None,
        retrieval_ms: float,
        first_token_ms: float | None,
        total_ms: float,
    ) -> DoneEvent:
        """El modelo escribió contenido y luego «No lo encuentro»: lo escrito no es de fiar."""
        log.warning("Respuesta contradictoria: contenido seguido de «%s»", NOT_FOUND)
        done = self._done(NOT_FOUND, stream, _EMPTY, finished, confidence, similarity,
                          retrieval_ms, first_token_ms, total_ms)  # fmt: skip
        warnings = tuple(w for w in done.warnings if w not in ("sin_citas", "citas_no_verificadas"))
        return replace(
            done, citations=(), invalid=(), warnings=(*warnings, "respuesta_contradictoria")
        )

    def _done(
        self,
        answer: str,
        stream: CitationStream,
        context: BuiltContext,
        finished: Finished | None,
        confidence: str,
        similarity: float | None,
        retrieval_ms: float,
        first_token_ms: float | None,
        total_ms: float,
    ) -> DoneEvent:
        report = stream.report
        not_found = answer.strip().startswith(NOT_FOUND)
        warnings: list[str] = []
        if not report.citations and not not_found:
            warnings.append("sin_citas")
        if report.only_hints:
            warnings.append("solo_pistas")
        if report.invalid:
            warnings.append("citas_no_verificadas")
        if finished is not None and finished.truncated:
            warnings.append("respuesta_truncada")
        if _context_cut_matters(context):
            warnings.append("contexto_recortado")
        if confidence == "baja":
            warnings.append("confianza_baja")

        tokens_per_second = None
        if finished is not None and finished.eval_ms > 0:
            tokens_per_second = finished.completion_tokens / (finished.eval_ms / 1000)
        timings = Timings(
            retrieval_ms=retrieval_ms,
            first_token_ms=first_token_ms,
            total_ms=total_ms,
            llm_load_ms=finished.load_ms if finished else None,
            tokens_per_second=tokens_per_second,
        )
        return DoneEvent(
            answer=answer,
            citations=tuple(report.citations),
            invalid=tuple(report.invalid),
            warnings=tuple(warnings),
            not_found=not_found,
            confidence=confidence,
            similarity=similarity,
            timings=timings,
            prompt_tokens=finished.prompt_tokens if finished else None,
            completion_tokens=finished.completion_tokens if finished else None,
        )
