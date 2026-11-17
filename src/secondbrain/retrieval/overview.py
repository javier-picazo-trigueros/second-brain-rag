"""Preguntas de visión general: en vez de buscar fragmentos, se resumen las notas de una
asignatura o de un tema con su `resumen`, sus conceptos y los apartados que contienen."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Protocol

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.exercises import ChunkSource, ExerciseBuilder, available_topics
from secondbrain.retrieval.families import CopyFamilies
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.intent import detect_intent
from secondbrain.retrieval.study import StudyPlanner
from secondbrain.retrieval.subjects import (
    Subject,
    SubjectIndex,
    SubjectSpec,
    load_aliases,
    norm,
    subject_of,
)
from secondbrain.retrieval.topics import index_topics, is_exercise, is_guide, topic_key, topics_fact
from secondbrain.store.manifest import Manifest

_COURSE = re.compile(r"^\d+º$")
_AMBIGUITY_RATIO = 0.75  # una fuente «igual de relevante» puntúa al menos esto sobre la mejor
_MIN_NUMBERED_TOPICS = (
    3  # a partir de aquí hay un temario numerado y solo él representa la asignatura
)
_NO_SUMMARY = "Sin resumen."
_HEADING_LEVELS = 2  # solo los dos primeros niveles de cada encabezado


class OutlineSource(Protocol):
    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]: ...


class Searcher(Protocol):
    def search(
        self,
        query: str,
        k: int = 5,
        *,
        with_graph: bool = True,
        only_paths: Sequence[str] | None = None,
    ) -> SearchResult: ...


def _natural_key(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", norm(text))]


def _course(path: str) -> str | None:
    first = path.split("/")[0]
    return first if _COURSE.match(first) else None


class OverviewBuilder:
    def __init__(
        self,
        settings: Settings,
        store: OutlineSource,
        manifest: Manifest,
        families: CopyFamilies | None = None,
    ) -> None:
        self._s = settings
        self._store = store
        self._manifest = manifest
        self._families = families or CopyFamilies(manifest)

    def build(
        self,
        notes: Sequence[str],
        headings: int,
        max_chars: int | None = None,
        facts: str = "",
        mode: str = "overview",
    ) -> SearchResult:
        """Una «nota» sintética por cada nota real, sin copias exactas y dentro del tope."""
        counts = self._manifest.chunk_counts()
        reps, copies = self._collapse(notes)
        chosen = self._choose(reps, counts)
        outline = self._store.outline(chosen)
        concepts = self._manifest.note_concepts()
        hits: list[NoteHit] = []
        for i, path in enumerate(chosen):
            own = sorted(
                (p for p in outline if p["note_path"] == path), key=lambda p: p["position"]
            )
            text = self._text(own, concepts.get(path, ()), headings)
            if max_chars is not None and len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
            payload: dict[str, Any] = {
                "note_path": path,
                "text": text,
                "asignatura": subject_of(path),
                "curso": _course(path),
                "heading_path": None,
                "page": None,
                "resumen": own[0].get("resumen") if own else None,
            }
            score = 1.0 - i / 1000
            hits.append(
                NoteHit(
                    path=path,
                    title=PurePosixPath(path).stem,
                    score=score,
                    raw_score=score,
                    chunks=(Hit(score, payload),),
                    also_in=copies.get(path, ()),
                    n_chunks=counts.get(path, 1),
                )
            )
        return SearchResult(hits, [], None, mode=mode, facts=facts)

    def _collapse(self, notes: Sequence[str]) -> tuple[list[str], dict[str, tuple[str, ...]]]:
        return self._families.collapse(notes)

    def _choose(self, reps: list[str], counts: Mapping[str, int]) -> list[str]:
        """Qué notas representan la asignatura (en orden natural).

        Fuera los libros (las «notas grandes» del ranking) y las guías docentes, salvo que no quede
        otra cosa. Si hay un temario numerado (Unit/Tema N, tres o más), solo entra el temario: la
        teoría de cada tema (las más grandes primero, con tope por tema) y, para un tema que solo
        tenga ejercicios, uno de ellos. Sin temario numerado, teoría antes que ejercicios.
        """

        def title(path: str) -> str:
            return PurePosixPath(path).stem

        usable = [
            p for p in reps if counts.get(p, 0) < self._s.big_note_chunks and not is_guide(title(p))
        ] or reps
        by_size = sorted(usable, key=lambda p: (-counts.get(p, 0), p))
        syllabus = {key[0] for p in usable if (key := topic_key(p)) is not None}
        per_key: dict[str, int] = {}
        theory: list[str] = []
        rest: list[str] = []
        for path in by_size:
            key = topic_key(path)
            if is_exercise(title(path)) or (
                key is not None and per_key.get(key[1], 0) >= self._s.overview_per_topic
            ):
                rest.append(path)
            else:
                if key is not None:
                    per_key[key[1]] = per_key.get(key[1], 0) + 1
                theory.append(path)
        if len(syllabus) >= _MIN_NUMBERED_TOPICS:
            covered = {key[0] for p in theory if (key := topic_key(p)) is not None}
            only_exercises = [
                next(p for p in rest if (k := topic_key(p)) is not None and k[0] == number)
                for number in sorted(syllabus - covered)
            ]
            kept = [p for p in theory if topic_key(p) is not None] + only_exercises
        else:
            kept = theory + rest
        return sorted(kept[: self._s.overview_max_notes], key=lambda p: _natural_key(title(p)))

    @staticmethod
    def _text(own: list[dict[str, Any]], concepts: Sequence[str], headings: int) -> str:
        resumen = next((str(p["resumen"]) for p in own if p.get("resumen")), _NO_SUMMARY)
        lines = [f"Resumen: {resumen}"]
        if concepts:
            lines.append(f"Conceptos: {', '.join(concepts)}")
        if headings > 0:
            seen: dict[str, None] = {}
            for p in own:
                parts = str(p.get("heading_path") or "").split(" > ")[:_HEADING_LEVELS]
                for part in parts:
                    if part:
                        seen.setdefault(part)
            if seen:
                lines.append(f"Apartados: {'; '.join(list(seen)[:headings])}")
        return "\n".join(lines)


class IntentRetriever:
    """Decide por pregunta: visión general de una asignatura o tema, o búsqueda híbrida normal."""

    def __init__(
        self,
        settings: Settings,
        base: Searcher,
        store: ChunkSource,
        manifest: Manifest,
        aliases: Mapping[str, SubjectSpec] | None = None,
        families: CopyFamilies | None = None,
    ) -> None:
        self._s = settings
        self._base = base
        self._manifest = manifest
        self._builder = OverviewBuilder(settings, store, manifest, families)
        self._exercises = ExerciseBuilder(settings, store, manifest, families)
        self._study = StudyPlanner(settings, store, manifest, families)
        self._aliases = load_aliases(settings.aliases_path) if aliases is None else aliases
        self._index_key: int | None = None
        self._index: SubjectIndex | None = None

    def _subjects(self) -> SubjectIndex:
        paths = self._manifest.paths()
        key = hash(frozenset(paths))
        if self._index is None or key != self._index_key:
            self._index = SubjectIndex(paths, self._aliases)
            self._index_key = key
        return self._index

    def search(self, query: str, k: int = 5, *, with_graph: bool = True) -> SearchResult:
        index = self._subjects()
        intent = detect_intent(query, index)
        if intent.subject is not None and intent.kind == "notes" and intent.topic is not None:
            return self._study_result(index, intent.subject, intent.topic)
        if intent.subject is not None and intent.kind == "exercises" and intent.topic is not None:
            return self._exercise_result(query, index, intent.subject, intent.topic)
        if intent.subject is not None and intent.kind != "search":
            if intent.topic is not None:
                notes = index.topic_notes(intent.subject, intent.topic)
                if notes:
                    return self._builder.build(
                        notes, self._s.overview_headings_topic, mode="overview_topic"
                    )
            else:
                every_note = index.notes_of(intent.subject)
                return self._builder.build(
                    every_note,
                    self._s.overview_headings_subject,
                    self._s.overview_text_chars,
                    facts=topics_fact(index_topics(every_note)),
                )
        named = index.detect_all(query)
        if intent.kind == "search" and len(named) >= 2:
            return self._cross(query, k, [index.notes_of(s) for s in named])
        result = self._base.search(query, k, with_graph=with_graph)
        if intent.subject is None and not named:
            return self._flag_ambiguity(index, result)
        return result

    def _flag_ambiguity(self, index: SubjectIndex, result: SearchResult) -> SearchResult:
        """Si las mejores fuentes, igual de relevantes, son de asignaturas distintas, el modelo
        debe decirlo al principio y responder con la más relevante (p. ej. «Euler» en grafos y en
        el método numérico)."""
        top = result.notes[:3]
        if len(top) < 2:
            return result
        close = [n for n in top if n.score >= _AMBIGUITY_RATIO * top[0].score]
        by_subject: dict[str, str] = {}
        for note in close:
            name = index.name_of(note.path)
            if name is not None:
                by_subject.setdefault(name, PurePosixPath(note.path).stem)
        if len(by_subject) < 2:
            return result
        listed = " y ".join(f"«{name}» ({title})" for name, title in by_subject.items())
        message = (
            "AMBIGÜEDAD: las fuentes más relevantes tratan temas distintos de asignaturas "
            f"distintas: {listed}. Empieza la respuesta con una primera frase que diga a qué "
            "asignaturas se refieren las fuentes y responde con la más relevante, sin mezclarlas."
        )
        facts = f"{result.facts}\n{message}" if result.facts else message
        return replace(result, facts=facts)

    def _study_result(self, index: SubjectIndex, subject: Subject, topic: int) -> SearchResult:
        notes = index.topic_notes(subject, topic)
        plan = self._study.plan(subject, topic, notes) if notes else None
        if plan is not None:
            return SearchResult([], [], None, mode="notes", study=plan)
        text = f"No encuentro apuntes del tema {topic} de {subject.name}."
        if not notes:
            have = available_topics(index.notes_of(subject))
            text += f" {subject.name} no tiene notas del tema {topic}."
            if have:
                text += f" Los temas que sí tiene son: {', '.join(str(n) for n in have)}."
        else:
            text += f" El tema {topic} solo tiene ejercicios o guías, no notas de teoría."
        return SearchResult([], [], None, mode="notes_none", canned=text)

    def _exercise_result(
        self, query: str, index: SubjectIndex, subject: Subject, topic: int
    ) -> SearchResult:
        notes = index.topic_notes(subject, topic)
        if not notes:
            return self._exercises.missing_topic(
                subject.name, topic, available_topics(index.notes_of(subject))
            )

        def theory(paths: Sequence[str]) -> list[NoteHit]:
            # La teoría se busca solo entre las notas de teoría de este tema y esta asignatura.
            return self._base.search(
                query, self._s.exercises_theory_notes, with_graph=False, only_paths=list(paths)
            ).notes

        return self._exercises.build(subject, topic, notes, theory, query)

    def _cross(self, query: str, k: int, groups: list[list[str]]) -> SearchResult:
        """Pregunta que cruza asignaturas: se busca en cada una y se intercalan los resultados,
        para que una no tape a la otra."""
        per = max(1, -(-k // len(groups)))
        results = [self._base.search(query, per, with_graph=False, only_paths=g) for g in groups]
        notes: list[NoteHit] = []
        for rank in range(per):
            notes.extend(r.notes[rank] for r in results if rank < len(r.notes))
        sims = [r.top_similarity for r in results if r.top_similarity is not None]
        return SearchResult(notes, [], max(sims) if sims else None)
