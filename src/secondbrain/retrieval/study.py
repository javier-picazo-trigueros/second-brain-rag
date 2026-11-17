"""Plan de unos apuntes del tema N de una asignatura: qué fragmentos reales entran en cada parte.

Se recorren, en orden de nota y de página, los fragmentos reales de las notas de TEORÍA del tema (no
sus resúmenes) troceados en ventanas que caben en el contexto del modelo; el «Resumen» del tema hace
de esqueleto que acompaña a cada parte. Las notas de ejercicios solo alimentan la última parte
(«Tipos de ejercicio»). Nunca entra una nota de otra asignatura o de otro tema.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

from secondbrain.answer.context import estimate_tokens
from secondbrain.config import Settings
from secondbrain.retrieval.exercises import ChunkSource, ExerciseBuilder
from secondbrain.retrieval.families import CopyFamilies
from secondbrain.retrieval.subjects import Subject, norm
from secondbrain.retrieval.topics import clean_title, is_guide, topic_key
from secondbrain.store.manifest import Manifest

_SUMMARY = re.compile(r"\b(?:resumen|resumenes|summary)\b")
_PART_TITLE_MAX = 80


@dataclass(frozen=True, slots=True)
class StudyFragment:
    id: str  # «S12»: numeración global de todos los apuntes
    label: str
    path: str
    title: str
    page: int | None
    heading: str | None
    text: str


@dataclass(frozen=True, slots=True)
class StudyPart:
    title: str
    kind: Literal["theory", "exercises"]
    fragments: tuple[StudyFragment, ...]


@dataclass(frozen=True, slots=True)
class StudyPlan:
    title: str
    subject: str
    topic: int
    skeleton: str  # texto del resumen del tema, si lo hay
    parts: tuple[StudyPart, ...]


def _natural(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", norm(text))]


def _syllabus_order(path: str) -> tuple[list[object], list[object]]:
    """Orden del temario: por apartado («3.1», «3.2»…) y, a igualdad, por nombre."""
    key = topic_key(path)
    return _natural(key[1] if key else ""), _natural(PurePosixPath(path).stem)


def _label(path: str, duplicated: set[str]) -> str:
    stem = PurePosixPath(path).stem
    return path.removesuffix(".md") if stem in duplicated else stem


class StudyPlanner:
    def __init__(
        self,
        settings: Settings,
        store: ChunkSource,
        manifest: Manifest,
        families: CopyFamilies | None = None,
    ) -> None:
        self._s = settings
        self._store = store
        self._families = families or CopyFamilies(manifest)
        self._exercises = ExerciseBuilder(settings, store, manifest, self._families)

    def plan(self, subject: Subject, topic: int, notes: Sequence[str]) -> StudyPlan | None:
        reps, _ = self._families.collapse(notes)
        exercises, theory = self._exercises.classify(reps)
        theory = [p for p in theory if not is_guide(PurePosixPath(p).stem)]
        summaries = [p for p in theory if _SUMMARY.search(norm(PurePosixPath(p).stem))]
        main = sorted((p for p in theory if p not in summaries), key=_syllabus_order)
        if not main:  # solo hay resumen: él es el contenido
            main, summaries = sorted(summaries, key=_syllabus_order), []
        if not main:
            return None

        stems = [PurePosixPath(p).stem for p in (*main, *summaries)]
        duplicated = {s for s in stems if stems.count(s) > 1}
        chunks = self._store.chunks_of([*summaries, *main])
        by_note: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            by_note.setdefault(str(chunk["note_path"]), []).append(chunk)

        skeleton = "\n".join(str(c["text"]) for p in summaries for c in by_note.get(p, ()))[
            : self._s.notes_skeleton_chars
        ].strip()

        windows = self._windows(
            [(p, c) for p in main for c in by_note.get(p, ())], self._s.notes_window_tokens
        )
        parts: list[StudyPart] = []
        counter = 0

        def numbered(group: list[tuple[str, dict[str, Any]]]) -> tuple[StudyFragment, ...]:
            nonlocal counter
            out: list[StudyFragment] = []
            for path, c in group:
                counter += 1
                page = c.get("page")
                heading = c.get("heading_path")
                out.append(
                    StudyFragment(
                        id=f"S{counter}",
                        label=_label(path, duplicated),
                        path=path,
                        title=PurePosixPath(path).stem,
                        page=int(page) if page is not None else None,
                        heading=str(heading) if heading else None,
                        text=str(c["text"]),
                    )
                )
            return tuple(out)

        for group in windows:
            fragments = numbered(group)
            parts.append(StudyPart(self._title(fragments), "theory", fragments))

        exercise_part = self._exercise_part(exercises, numbered)
        if exercise_part is not None:
            parts.append(exercise_part)
        return StudyPlan(
            title=f"Apuntes del tema {topic} de {subject.name}",
            subject=subject.name,
            topic=topic,
            skeleton=skeleton,
            parts=tuple(parts),
        )

    @staticmethod
    def _windows(
        items: list[tuple[str, dict[str, Any]]], budget: int
    ) -> list[list[tuple[str, dict[str, Any]]]]:
        out: list[list[tuple[str, dict[str, Any]]]] = []
        current: list[tuple[str, dict[str, Any]]] = []
        used = 0
        for item in items:
            cost = estimate_tokens(str(item[1]["text"]))
            if current and used + cost > budget:
                out.append(current)
                current, used = [], 0
            current.append(item)
            used += cost
        if current:
            out.append(current)
        return out

    @staticmethod
    def _title(fragments: Sequence[StudyFragment]) -> str:
        """«Nota · págs. 4-28»: dónde está lo que se va a escribir (los encabezados del PDF
        convertido, a menudo «**ASIGNATURA**», no sirven de título)."""
        first = fragments[0]
        name = clean_title(first.title).replace("*", "").strip() or first.title
        pages = [f.page for f in fragments if f.page is not None]
        if not pages:
            return name[:_PART_TITLE_MAX]
        low, high = min(pages), max(pages)
        span = f"{low}" if low == high else f"{low}-{high}"
        return f"{name[: _PART_TITLE_MAX - 16]} · págs. {span}"

    def _exercise_part(
        self,
        exercises: Sequence[Any],
        numbered: Any,
    ) -> StudyPart | None:
        order = [path for ex in exercises for path in ex.paths]
        if not order:
            return None
        by_note: dict[str, list[dict[str, Any]]] = {}
        for chunk in self._store.chunks_of(order):
            by_note.setdefault(str(chunk["note_path"]), []).append(chunk)
        group: list[tuple[str, dict[str, Any]]] = []
        used = 0
        for path in order:
            for chunk in by_note.get(path, ()):
                used += estimate_tokens(str(chunk["text"]))
                if group and used > self._s.notes_window_tokens:
                    break
                group.append((path, chunk))
        if not group:
            return None
        return StudyPart("Tipos de ejercicio", "exercises", numbered(group))
