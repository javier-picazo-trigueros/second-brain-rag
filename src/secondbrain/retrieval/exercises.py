"""Modo «ejercicios»: resolver o explicar los ejercicios del tema N de una asignatura.

La recuperación se acota a esa asignatura y a ese tema: primero los enunciados (cada uno seguido de
su solución, si existe), con su texto real y completo, y después la teoría del tema para justificar
los pasos. Nunca entra una nota de otra asignatura o de otro tema. Si el tema no tiene ejercicios,
la respuesta es fija y no pasa por el modelo.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Any, Protocol

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.families import CopyFamilies, base_title
from secondbrain.retrieval.hybrid import NoteHit, SearchResult
from secondbrain.retrieval.subjects import Subject, norm
from secondbrain.retrieval.topics import clean_title, is_exercise, is_guide, is_solution, topic_key
from secondbrain.store.manifest import Manifest

TheorySearch = Callable[[Sequence[str]], list[NoteHit]]

_SOLUTION_WORDS = re.compile(r"\b(?:solutions?|soluciones|solucion(?:es|ario)?)\b")
_NAMED = re.compile(r"\b(?:ejercicio|problema)s?\s*(?:numero\s*)?(\d{1,2})\b")


class ChunkSource(Protocol):
    def outline(self, paths: Sequence[str]) -> list[dict[str, Any]]: ...

    def chunks_of(self, paths: Sequence[str]) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class _Exercise:
    key: str
    title: str
    statements: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [*self.statements, *self.solutions]


def _pair_key(stem: str) -> str:
    """Clave común del enunciado y de su solución («… exercises 1» y «… exercises 1 - solution»)."""
    plain = norm(base_title(stem))
    return " ".join(_SOLUTION_WORDS.sub(" ", plain).split())


def _natural(key: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", key) if t]


def _pick(exercises: Sequence[_Exercise], question: str) -> int:
    """Ejercicio a resolver: el que nombra la pregunta («el ejercicio 2») o el primero."""
    named = _NAMED.search(norm(question))
    if named is not None and 1 <= int(named.group(1)) <= len(exercises):
        return int(named.group(1)) - 1
    return 0


def no_exercises_text(subject: str, topic: int, titles: Sequence[str]) -> str:
    """Respuesta fija cuando el tema no tiene ejercicios (o no existe)."""
    head = f"No encuentro ejercicios del tema {topic} de {subject}."
    if titles:
        listed = "\n".join(f"- {t}" for t in titles)
        body = f"Del tema {topic} tienes:\n{listed}"
    else:
        body = f"{subject} no tiene notas del tema {topic}."
    offer = "¿Quieres que te explique la teoría de ese tema o que te haga unos apuntes?"
    if not titles:
        offer = "¿Quieres que te cuente qué temas tiene la asignatura?"
    return f"{head}\n\n{body}\n\n{offer}"


class ExerciseBuilder:
    def __init__(
        self,
        settings: Settings,
        store: ChunkSource,
        manifest: Manifest,
        families: CopyFamilies | None = None,
    ) -> None:
        self._s = settings
        self._store = store
        self._manifest = manifest
        self._families = families or CopyFamilies(manifest)

    def build(
        self,
        subject: Subject,
        topic: int,
        notes: Sequence[str],
        theory: TheorySearch,
        question: str = "",
    ) -> SearchResult:
        """Evidencia de los ejercicios del tema, o la respuesta fija si no hay ninguno."""
        reps, copies = self._families.collapse(notes)
        exercises, theory_paths = self.classify(reps)
        if not exercises:
            return self._none(subject.name, topic, reps)

        chosen = _pick(exercises, question)
        order = exercises[chosen].paths
        by_note: dict[str, list[dict[str, Any]]] = {}
        for chunk in self._store.chunks_of(order):
            by_note.setdefault(str(chunk["note_path"]), []).append(chunk)
        hits: list[NoteHit] = []
        for path in order:
            chunks = tuple(Hit(1.0, c) for c in by_note.get(path, ()))
            if not chunks:
                continue
            score = 1.0 - len(hits) / 1000
            hits.append(
                NoteHit(
                    path=path,
                    title=PurePosixPath(path).stem,
                    score=score,
                    raw_score=score,
                    chunks=chunks,
                    also_in=copies.get(path, ()),
                    n_chunks=len(chunks),
                )
            )
        if theory_paths and self._s.exercises_theory_notes > 0:
            hits.extend(theory(theory_paths)[: self._s.exercises_theory_notes])
        return SearchResult(
            hits, [], None, mode="exercises", facts=self._facts(subject, topic, exercises, chosen)
        )

    def classify(self, reps: Sequence[str]) -> tuple[list[_Exercise], list[str]]:
        grouped: dict[str, _Exercise] = {}
        theory: list[str] = []
        for path in sorted(reps):
            stem = PurePosixPath(path).stem
            if is_guide(stem):
                continue
            if not (is_exercise(stem) or is_solution(stem)):
                theory.append(path)
                continue
            key = _pair_key(stem)
            item = grouped.setdefault(key, _Exercise(key, clean_title(stem)))
            (item.solutions if is_solution(stem) else item.statements).append(path)
        exercises = sorted(grouped.values(), key=lambda e: _natural(e.key))
        for item in exercises:
            if item.statements:
                item.title = clean_title(PurePosixPath(item.statements[0]).stem)
            else:  # solo hay la nota de soluciones: hace de enunciado
                item.title = _SOLUTION_WORDS.sub(
                    "", clean_title(PurePosixPath(item.solutions[0]).stem)
                )
                item.title = item.title.strip(" -_.") or item.key
        return exercises, theory

    @staticmethod
    def _facts(subject: Subject, topic: int, exercises: Sequence[_Exercise], chosen: int) -> str:
        n = len(exercises)
        noun = "ejercicio" if n == 1 else "ejercicios"
        listed = "; ".join(
            f"{i}) {e.title} ({'con solución' if e.solutions else 'sin solución'})"
            for i, e in enumerate(exercises, start=1)
        )
        head = f"DATO DEL ÍNDICE: el tema {topic} de {subject.name} tiene {n} {noun}: {listed}."
        number = chosen + 1
        solve = (
            f" Resuelve SOLO el ejercicio {number} ({exercises[chosen].title}): resuélvelo "
            "COMPLETO, paso a paso."
        )
        others = [i for i in range(n) if i != chosen]
        if others:
            following = next((i for i in others if i > chosen), others[0]) + 1
            rest = ", ".join(f"ejercicio {i + 1}" for i in others)
            solve += (
                f" Cuando termines, lista los demás ({rest}) y pregunta: «¿Sigo con el ejercicio "
                f"{following}?», indicando que se pide así: «resuelve el ejercicio {following} "
                f"del tema {topic} de {subject.name}»."
            )
        return (
            f"{head}{solve} Las fuentes llevan el enunciado y la solución de ese ejercicio y "
            "fragmentos de teoría del tema."
        )

    def _none(self, subject: str, topic: int, reps: Sequence[str]) -> SearchResult:
        """Sin ejercicios: las notas del tema (si las hay) como fuentes y el texto fijo."""
        titles = [PurePosixPath(p).stem for p in reps if not is_guide(PurePosixPath(p).stem)]
        text = no_exercises_text(subject, topic, titles)
        if not titles:
            return SearchResult([], [], None, mode="exercises_none", canned=text)
        from secondbrain.retrieval.overview import OverviewBuilder  # evita el ciclo de imports

        shown = OverviewBuilder(self._s, self._store, self._manifest, self._families).build(
            reps, 0, mode="exercises_none"
        )
        return replace(shown, canned=text)

    def missing_topic(self, subject: str, topic: int, available: Sequence[int]) -> SearchResult:
        """El tema no existe en la asignatura: lo dice y menciona los que sí tiene."""
        text = no_exercises_text(subject, topic, [])
        if available:
            listed = ", ".join(str(n) for n in available)
            text = text.replace(
                f"{subject} no tiene notas del tema {topic}.",
                f"{subject} no tiene notas del tema {topic}. Los temas que sí tiene son: {listed}.",
            )
        return SearchResult([], [], None, mode="exercises_none", canned=text)


def available_topics(paths: Sequence[str]) -> list[int]:
    return sorted({key[0] for p in paths if (key := topic_key(p)) is not None})
