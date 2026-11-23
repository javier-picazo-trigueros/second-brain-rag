from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Protocol

from secondbrain.answer.citations import CitationStream
from secondbrain.answer.context import BuiltContext, Fragment, Source, build_context
from secondbrain.answer.llm import LLM, Delta, Finished, LLMError, Message
from secondbrain.answer.prompt import (
    NOT_FOUND,
    QUESTION_MAX_CHARS,
    build_continuation_messages,
    build_messages,
    build_study_messages,
)
from secondbrain.config import Settings
from secondbrain.retrieval.hybrid import SearchResult
from secondbrain.retrieval.study import StudyPlan

log = logging.getLogger(__name__)

_EMPTY = BuiltContext("", (), 0, 0, "search", ())

_MIN_PROGRESS_CHARS = 40  # una continuación con menos texto nuevo que esto «no avanza»
_HOLD_CHARS = 400  # al continuar se retiene el arranque para quitar lo que repite del final
_MIN_OVERLAP = 15  # solape mínimo (caracteres) para considerar que el modelo repite lo escrito
_SENTENCE_STOP = ".!?:;)]"
_LIST_START = "-*#|>"


def _drop_overlap(previous: str, new: str) -> str:
    """Quita del arranque de `new` lo que repite el final de `previous` (el modelo, al continuar,
    suele volver a escribir la frase en la que se cortó)."""
    body = new.lstrip()
    longest = min(len(previous), len(body), 1500)
    for size in range(longest, _MIN_OVERLAP - 1, -1):
        if previous.endswith(body[:size]):
            return body[size:]
    return new


def _join(previous: str, new: str) -> str:
    """Texto de la continuación con el separador que pide el empalme: un corte en mitad de una
    palabra se une tal cual; tras el final de una frase, con un espacio o un salto de línea."""
    if not previous or not new or previous[-1].isspace() or new[0].isspace():
        return new
    if previous[-1] not in _SENTENCE_STOP:
        return new
    return ("\n" if new[0] in _LIST_START else " ") + new


@dataclass(slots=True)
class _Attempt:
    """Resultado de una llamada al modelo para una parte de los apuntes."""

    text: str = ""
    finished: Finished | None = None


PARTIAL_NOTE = "No he encontrado en tus apuntes el resto de lo que preguntas."
_CITED = re.compile(r"\[S\d{1,3}\]")
_LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _salvage(text: str) -> str:
    """De lo escrito antes de «No lo encuentro»: solo las líneas de lista y las frases que llevan
    una cita verificada (las citas no válidas ya vienen marcadas y no cuentan)."""
    kept: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        if _LIST_LINE.match(line):
            if _CITED.search(line):
                kept.append(line.rstrip())
            continue
        sentences = [x for x in _SENTENCE_END.split(line.strip()) if _CITED.search(x)]
        if sentences:
            kept.append(" ".join(sentences))
    return "\n".join(kept)


# Números que merecen comprobación: con decimales, o enteros de tres cifras o más (no «paso 2»).
_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?(?![\w])")
_HEADER_LINE = re.compile(
    r"^(?:###|Nota:|Página:|Encabezado:|Asignatura:|Curso:|DATO DEL ÍNDICE).*$", re.M
)
_STEP = re.compile(r"^\s{0,3}(?:[*_]{0,2}Paso\s+\d+|\d+[.)])\s?", re.I)


def _values(text: str) -> list[tuple[str, float, int]]:
    out: list[tuple[str, float, int]] = []
    for match in _NUMBER.finditer(text):
        raw = match.group(0)
        number = raw.replace(",", ".")
        decimals = len(number.split(".")[1].split("e")[0].split("E")[0]) if "." in number else 0
        if "." not in number and "e" not in number.lower() and len(number) < 3:
            continue  # contadores y números de paso
        try:
            out.append((raw, float(number), decimals))
        except ValueError:
            continue
    return out


def _unverified_numbers(answer: str, sources: str) -> tuple[str, ...]:
    """Números de la respuesta que no aparecen en las fuentes (ni como 100 veces o la centésima
    parte de uno de ellos: así se pasa de fracción a porcentaje). El modelo copia, no recalcula."""
    known = [v for _, v, _ in _values(_HEADER_LINE.sub("", sources))]
    wanted = {*known, *(k * 100 for k in known), *(k / 100 for k in known)}
    out: dict[str, None] = {}
    for raw, value, decimals in _values(_CITED.sub("", answer)):
        if not any(round(w, decimals) == round(value, decimals) for w in wanted):
            out.setdefault(raw)
    return tuple(out)


def _uncited_steps(answer: str) -> int:
    """Pasos («Paso 2», «2.») cuyo bloque, hasta el siguiente paso, no lleva ninguna cita."""
    blocks: list[list[str]] = []
    for line in answer.split("\n"):
        if _STEP.match(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return sum(1 for block in blocks if not _CITED.search("\n".join(block)))


def _study_sources(plan: StudyPlan) -> tuple[Source, ...]:
    """Una fuente por nota usada, con las páginas de sus fragmentos."""
    pages: dict[str, list[int]] = {}
    labels: dict[str, tuple[str, str]] = {}
    for part in plan.parts:
        for f in part.fragments:
            labels.setdefault(f.path, (f.label, f.title))
            pages.setdefault(f.path, [])
            if f.page is not None and f.page not in pages[f.path]:
                pages[f.path].append(f.page)
    out: list[Source] = []
    for path, (label, title) in labels.items():
        first = path.split("/")[0]
        out.append(
            Source(
                label=label,
                path=path,
                title=title,
                kind="evidence",
                pages=tuple(sorted(pages[path])),
                asignatura=plan.subject,
                curso=first if first.endswith("º") else None,
                truncated=False,
            )
        )
    return tuple(out)


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
class ProgressEvent:
    """Modo apuntes: se va a escribir la parte `part` de `total` (empieza en 1)."""

    part: int
    total: int
    title: str


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
    mode: str = "search"  # «notes»: apuntes (se pueden guardar como nota)
    subject: str | None = None
    topic: int | None = None
    # Modo ejercicios: números de la respuesta que no salen de las fuentes y pasos sin cita.
    unverified_numbers: tuple[str, ...] = ()
    uncited_steps: int = 0


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str


Event = SourcesEvent | ProgressEvent | TokenEvent | DoneEvent | ErrorEvent


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
        clipped = len(question) > QUESTION_MAX_CHARS
        for event in self._ask(question[:QUESTION_MAX_CHARS], k):
            if clipped and isinstance(event, DoneEvent):
                event = replace(event, warnings=(*event.warnings, "pregunta_recortada"))
            yield event

    def _ask(self, question: str, k: int | None) -> Iterator[Event]:
        start = self._clock()
        result, context = self.plan(question, k)
        retrieval_ms = (self._clock() - start) * 1000
        confidence = confidence_label(result.top_similarity, self._s.confidence_threshold)
        if result.study is not None:
            yield from self._write_study(result.study, start, retrieval_ms)
            return
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

        if context.mode == "exercises":
            yield from self._ask_exercises(
                question, context, confidence, result.top_similarity, start, retrieval_ms
            )
            return

        prefix = f"{result.ambiguity}\n\n" if result.ambiguity else ""
        if prefix:
            yield TokenEvent(prefix)  # la dice el sistema, no el modelo: no depende de que obedezca
        stream = CitationStream(context.fragments)
        parts: list[str] = []
        first_token_ms: float | None = None
        finished: Finished | None = None
        try:
            limit = self._s.exercises_max_tokens if context.mode == "exercises" else None
            for item in self._llm.stream_chat(build_messages(question, context), limit):
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
            dropped = self._contradictory(
                answer, stream, context, finished, confidence, result.top_similarity,
                retrieval_ms, first_token_ms, (self._clock() - start) * 1000,
            )  # fmt: skip
            yield replace(dropped, answer=prefix + dropped.answer) if prefix else dropped
            return
        done = self._done(
            "".join(parts), stream, context, finished, confidence, result.top_similarity,
            retrieval_ms, first_token_ms, (self._clock() - start) * 1000,
        )  # fmt: skip
        yield replace(done, answer=prefix + done.answer) if prefix else done

    def _ask_exercises(
        self,
        question: str,
        context: BuiltContext,
        confidence: str,
        similarity: float | None,
        start: float,
        retrieval_ms: float,
    ) -> Iterator[Event]:
        """Ejercicios: se genera la respuesta completa y se comprueba que cada paso cita su fuente.
        Si no (el modelo de 7B se olvida de citar), se le pide una vez más avisándole de qué falló.
        El usuario ve solo la mejor de las dos, no el intento fallido."""
        base = build_messages(question, context)
        best: tuple[tuple[int, int], str, CitationStream, Finished | None] | None = None
        nudge = ""
        for _attempt in range(2):
            messages = [*base[:-1], Message("user", base[-1].content + nudge)] if nudge else base
            stream = CitationStream(context.fragments)
            parts: list[str] = []
            finished: Finished | None = None
            try:
                for item in self._llm.stream_chat(messages, self._s.exercises_max_tokens):
                    if isinstance(item, Delta):
                        piece = stream.feed(item.text)
                    else:
                        finished, piece = item, ""
                    if piece:
                        parts.append(piece)
                        if _contradiction("".join(parts)):
                            break
                if not _contradiction("".join(parts)):
                    parts.append(stream.finish())
            except LLMError as exc:
                log.warning("Fallo del modelo: %s", exc)
                yield ErrorEvent(str(exc))
                return
            text = "".join(parts)
            if _contradiction(text):
                done = self._contradictory(
                    text, stream, context, finished, confidence, similarity,
                    retrieval_ms, None, (self._clock() - start) * 1000,
                )  # fmt: skip
                yield TokenEvent(done.answer)
                yield done
                return
            uncited = _uncited_steps(text)
            cited = len(stream.report.citations)
            score = (0 if cited else 1, uncited)
            if best is None or score < best[0]:
                best = (score, text, stream, finished)
            if cited and not uncited:
                break
            problems = []
            if not cited:
                problems.append("ninguna cita")
            if uncited:
                problems.append(
                    f"{uncited} {'paso sin cita' if uncited == 1 else 'pasos sin cita'}"
                )
            nudge = (
                f"\n\nAVISO: tu respuesta anterior tenía {' y '.join(problems)}. Escríbela de "
                "nuevo: cada «Paso N» termina con su cita [S#] (copiada de las FUENTES) y los "
                "números se copian de la solución, sin recalcular."
            )
        assert best is not None
        _, text, stream, finished = best
        first_token_ms = (self._clock() - start) * 1000
        yield TokenEvent(text)
        yield self._done(
            text, stream, context, finished, confidence, similarity,
            retrieval_ms, first_token_ms, (self._clock() - start) * 1000,
        )  # fmt: skip

    def _write_study(self, plan: StudyPlan, start: float, retrieval_ms: float) -> Iterator[Event]:
        """Apuntes: una llamada al modelo por parte, con su ventana de fragmentos reales."""
        fragments = tuple(
            Fragment(f.id, f.label, f.path, f.title, "evidence", f.page, f.heading)
            for part in plan.parts
            for f in part.fragments
        )
        sources = _study_sources(plan)
        yield SourcesEvent(sources, fragments, "desconocida", None, 0)

        heading = f"# {plan.title}"
        pieces = [heading]
        yield TokenEvent(f"{heading}\n\n")
        citations: dict[str, Fragment] = {}
        invalid: dict[str, None] = {}
        warnings: dict[str, None] = {}
        total_tokens = 0
        first_token_ms: float | None = None
        for number, part in enumerate(plan.parts, start=1):
            yield ProgressEvent(number, len(plan.parts), part.title)
            ids = {f.id for f in part.fragments}
            part_fragments = tuple(f for f in fragments if f.id in ids)
            part_head = f"## {part.title}\n\n"
            if number > 1:
                yield TokenEvent("\n\n")  # separa de la parte anterior
            yield TokenEvent(part_head)
            body = ""
            attempt = 0
            part_citations: dict[str, Fragment] = {}
            part_invalid: dict[str, None] = {}
            part_tokens = 0
            unfinished = False
            messages = build_study_messages(plan, part, number, len(plan.parts))
            while True:
                stream = CitationStream(part_fragments)
                run = _Attempt()
                try:
                    for event in self._write_attempt(messages, stream, body, attempt > 0, run):
                        if first_token_ms is None and isinstance(event, TokenEvent):
                            first_token_ms = (self._clock() - start) * 1000
                        yield event
                except LLMError as exc:
                    log.warning("Fallo del modelo: %s", exc)
                    yield ErrorEvent(str(exc))
                    return
                body += run.text
                for fragment in stream.report.citations:
                    part_citations.setdefault(fragment.id, fragment)
                part_invalid.update(dict.fromkeys(stream.report.invalid))
                if run.finished is not None:
                    part_tokens += run.finished.completion_tokens
                if _contradiction(body) or not (run.finished and run.finished.truncated):
                    break
                # Cortada por el tope de salida: se continúa con las mismas fuentes y el final de lo
                # escrito, salvo que se haya agotado el límite o la continuación no avance.
                stuck = attempt > 0 and len(run.text.strip()) < _MIN_PROGRESS_CHARS
                if attempt >= self._s.notes_max_continuations or stuck:
                    unfinished = True
                    log.warning(
                        "Parte sin terminar tras %d continuaciones: %s", attempt, part.title
                    )
                    break
                attempt += 1
                log.info("Continuando la parte %d (corte %d)", number, attempt)
                messages = build_continuation_messages(plan, part, number, len(plan.parts), body)
            if _contradiction(body):
                warnings["respuesta_contradictoria"] = None
                continue  # lo escrito en esta parte no es de fiar: no entra en los apuntes
            if unfinished:
                warnings["parte_sin_terminar"] = None
            total_tokens += part_tokens
            for fragment in part_citations.values():
                citations.setdefault(fragment.id, fragment)
            invalid.update(part_invalid)
            pieces.append(f"{part_head.rstrip()}\n\n{body.strip()}")

        if invalid:
            warnings["citas_no_verificadas"] = None
        if not citations:
            warnings["sin_citas"] = None
        yield DoneEvent(
            answer="\n\n".join(pieces),
            citations=tuple(citations.values()),
            invalid=tuple(invalid),
            warnings=tuple(warnings),
            not_found=False,
            confidence="desconocida",
            similarity=None,
            timings=Timings(
                retrieval_ms, first_token_ms, (self._clock() - start) * 1000, None, None
            ),
            prompt_tokens=None,
            completion_tokens=total_tokens or None,
            mode="notes",
            subject=plan.subject,
            topic=plan.topic,
        )

    def _write_attempt(
        self,
        messages: list[Message],
        stream: CitationStream,
        previous: str,
        continuing: bool,
        run: _Attempt,
    ) -> Iterator[Event]:
        """Una llamada al modelo para una parte. Al continuar se retiene el arranque hasta poder
        quitar lo repetido; lo que se emite es exactamente lo que se añade a `run.text`."""
        held: list[str] = []
        released = not continuing
        emitted: list[str] = []

        def emit(text: str) -> Iterator[Event]:
            if not text:
                return
            emitted.append(text)
            yield TokenEvent(text)

        def release() -> Iterator[Event]:
            joined = "".join(held)
            held.clear()
            yield from emit(_join(previous, _drop_overlap(previous, joined)))

        contradictory = False
        for item in self._llm.stream_chat(messages, self._s.notes_part_max_tokens):
            if isinstance(item, Delta):
                piece = stream.feed(item.text)
            else:
                run.finished, piece = item, ""
            if not piece:
                continue
            if released:
                yield from emit(piece)
                if _contradiction(previous + "".join(emitted)):
                    contradictory = True
                    break
            else:
                held.append(piece)
                if sum(map(len, held)) >= _HOLD_CHARS:
                    released = True
                    yield from release()
        if not contradictory:
            tail = stream.finish()
            if run.finished is not None and run.finished.truncated:
                tail = re.sub(r"\[[^\]\n]*$", "", tail)  # una cita cortada por el tope
            if released:
                yield from emit(tail)
            else:
                held.append(tail)
                yield from release()
        run.text = "".join(emitted)

    def _contradictory(
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
        """El modelo escribió contenido y luego «No lo encuentro». Si algunas frases llevan citas
        verificadas se conservan solo ellas y la respuesta se marca como parcial; si no, lo escrito
        no es de fiar y se descarta entera."""
        log.warning("Respuesta contradictoria: contenido seguido de «%s»", NOT_FOUND)
        kept = _salvage(answer[: answer.find(NOT_FOUND)])
        if kept:
            text = f"{kept}\n\n{PARTIAL_NOTE}"
            done = self._done(text, stream, context, finished, confidence, similarity,
                              retrieval_ms, first_token_ms, total_ms)  # fmt: skip
            ids = set(re.findall(r"\[(S\d{1,3})\]", kept))
            warnings = tuple(
                w for w in done.warnings if w not in ("sin_citas", "citas_no_verificadas")
            )
            return replace(
                done,
                citations=tuple(f for f in context.fragments if f.id in ids),
                invalid=(),
                warnings=(*warnings, "respuesta_parcial"),
            )
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
        unverified: tuple[str, ...] = ()
        uncited = 0
        if context.mode == "exercises" and not not_found:
            unverified = _unverified_numbers(answer, context.text)
            uncited = _uncited_steps(answer)
            if unverified:
                warnings.append("numeros_no_verificados")
            if uncited:
                warnings.append("pasos_sin_cita")

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
            unverified_numbers=unverified,
            uncited_steps=uncited,
        )
