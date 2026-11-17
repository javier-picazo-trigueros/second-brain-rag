"""Asignaturas del vault: carpeta de asignatura, alias que usa el usuario y sus notas."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

_COURSE = re.compile(r"^\d+º$")
_EXACT_MAX = 3  # palabras de hasta 3 letras (y números): sin tolerancia a faltas
_FUZZY_MIN_SINGLE = 6  # un alias de una sola palabra necesita al menos 6 letras para tolerar faltas
_FUZZY_RATIO = 0.8
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def norm(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación, espacios colapsados."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", plain).strip()


def _close(alias_word: str, word: str) -> bool:
    if alias_word == word:
        return True
    if len(alias_word) <= _EXACT_MAX or len(word) <= _EXACT_MAX:
        return False
    return SequenceMatcher(None, alias_word, word).ratio() >= _FUZZY_RATIO


def subject_of(path: str) -> str | None:
    """Carpeta de asignatura de una nota: `curso/ASIGNATURA/...` -> ASIGNATURA.

    Es la de segundo nivel, no la inmediata (`3º/DM/PWI/x.md` es DM). Sin curso, la primera.
    """
    parts = path.split("/")
    if _COURSE.match(parts[0]):
        return parts[1] if len(parts) >= 3 else None
    return parts[0] if len(parts) >= 2 else None


def display_subject(path: str, frontmatter_value: object) -> str | None:
    """Asignatura que se muestra de una nota: su carpeta de asignatura; el frontmatter solo si la
    nota está fuera de una (el campo suele ser la subcarpeta inmediata: «images», «Parte1»...)."""
    return subject_of(path) or (str(frontmatter_value) if frontmatter_value else None)


@dataclass(frozen=True, slots=True)
class SubjectSpec:
    """Entrada del fichero de alias: cómo nombra el usuario una asignatura y dónde está."""

    aliases: tuple[str, ...] = ()
    folders: tuple[str, ...] = ()  # carpetas de asignatura que la forman (se fusionan)
    include: tuple[str, ...] = ()  # fragmentos de ruta extra (notas sueltas en otra carpeta)


def _strings(table: Mapping[str, object], key: str, name: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"Alias de {name!r}: `{key}` debe ser una lista de textos")
    return tuple(value)


def load_aliases(path: Path) -> dict[str, SubjectSpec]:
    """Lee `data/aliases.toml`. Sin fichero, no hay alias manuales (solo los de las carpetas)."""
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: dict[str, SubjectSpec] = {}
    for name, table in data.get("subjects", {}).items():
        out[name] = SubjectSpec(
            aliases=_strings(table, "aliases", name),
            folders=_strings(table, "folders", name),
            include=_strings(table, "include", name),
        )
    return out


@dataclass(frozen=True, slots=True)
class Subject:
    name: str
    aliases: tuple[str, ...]  # normalizados
    folders: frozenset[str]  # carpetas de asignatura normalizadas
    include: tuple[str, ...]  # fragmentos de ruta normalizados


def _topic_pattern(n: int) -> re.Pattern[str]:
    return re.compile(rf"(?<![0-9a-z])(?:tema|unidad|unit|capitulo)\s*0?{n}(?!\d)")


class SubjectIndex:
    def __init__(
        self, note_paths: Iterable[str], extra: Mapping[str, SubjectSpec] | None = None
    ) -> None:
        self._paths = sorted(set(note_paths))
        self._subjects = self._build(extra or {})
        # Un `include` mueve la nota: la reclama su asignatura y las demás no la cogen por carpeta.
        claimed = {p: s.name for s in self._subjects for p in self._paths if self._included(s, p)}
        self._notes = {s.name: self._collect(s, claimed) for s in self._subjects}
        self._owner = {path: name for name, notes in self._notes.items() for path in notes}

    def _build(self, extra: Mapping[str, SubjectSpec]) -> list[Subject]:
        spelled: dict[str, Counter[str]] = {}
        for path in self._paths:
            folder = subject_of(path)
            if folder:
                spelled.setdefault(norm(folder), Counter())[folder] += 1
        subjects: list[Subject] = []
        absorbed: set[str] = set()
        for name, spec in extra.items():
            folders = frozenset(norm(f) for f in spec.folders)
            absorbed |= folders
            aliases = {norm(a) for a in (name, *spec.aliases)}
            subjects.append(
                Subject(name, tuple(sorted(aliases)), folders, tuple(norm(i) for i in spec.include))
            )
        for key, spellings in spelled.items():
            if key not in absorbed:
                subjects.append(
                    Subject(spellings.most_common(1)[0][0], (key,), frozenset({key}), ())
                )
        return subjects

    @staticmethod
    def _included(subject: Subject, path: str) -> bool:
        return any(frag in norm(path) for frag in subject.include)

    def _collect(self, subject: Subject, claimed: Mapping[str, str]) -> list[str]:
        return [
            p
            for p in self._paths
            if claimed.get(p) == subject.name
            or (norm(subject_of(p) or "") in subject.folders and p not in claimed)
        ]

    def subjects(self) -> list[Subject]:
        return list(self._subjects)

    def name_of(self, path: str) -> str | None:
        """Asignatura canónica de la nota (None si no está en una carpeta de asignatura)."""
        return self._owner.get(path)

    def by_name(self, name: str) -> Subject | None:
        key = norm(name)
        return next((s for s in self._subjects if key in s.aliases or norm(s.name) == key), None)

    def detect(self, question: str) -> Subject | None:
        """Asignatura que nombra la pregunta (alias más largo; palabras completas).

        Si no aparece tal cual, se tolera una falta de ortografía en las palabras largas
        («artificicial», «mineria de datoss»); las cortas y los números («I», «II», «2») deben
        coincidir exactos, para que un fallo nunca convierta «IA II» en «IA I».
        """
        text = norm(question)
        padded = f" {text} "
        best: tuple[int, int, Subject] | None = None
        for subject in self._subjects:
            for alias in subject.aliases:
                if f" {alias} " in padded:
                    rank = (len(alias), len(self._notes[subject.name]))
                    if best is None or rank > best[:2]:
                        best = (*rank, subject)
        return best[2] if best else self._detect_fuzzy(text.split())

    def _detect_fuzzy(self, words: list[str]) -> Subject | None:
        best: tuple[int, int, Subject] | None = None
        for subject in self._subjects:
            for alias in subject.aliases:
                tokens = alias.split()
                if all(len(t) <= _EXACT_MAX for t in tokens) or (
                    len(tokens) == 1 and len(tokens[0]) < _FUZZY_MIN_SINGLE
                ):
                    continue
                for start in range(len(words) - len(tokens) + 1):
                    window = words[start : start + len(tokens)]
                    if all(_close(a, b) for a, b in zip(tokens, window, strict=True)):
                        rank = (len(alias), len(self._notes[subject.name]))
                        if best is None or rank > best[:2]:
                            best = (*rank, subject)
        return best[2] if best else None

    def detect_all(self, question: str) -> list[Subject]:
        """Todas las asignaturas que nombra la pregunta, en orden de aparición.

        Un alias contenido en otro más largo (p. ej. «sistemas» en «sistemas operativos») no cuenta.
        """
        text = f" {norm(question)} "
        spans: list[tuple[int, int, Subject]] = []
        for subject in self._subjects:
            for alias in subject.aliases:
                start = text.find(f" {alias} ")
                if start >= 0:
                    spans.append((start, start + len(alias) + 2, subject))
        accepted: list[tuple[int, int, Subject]] = []
        for start, end, subject in sorted(spans, key=lambda s: s[0] - s[1]):  # más largos primero
            if all(end <= a or start >= b for a, b, _ in accepted) and all(
                subject is not other for _, _, other in accepted
            ):
                accepted.append((start, end, subject))
        return [subject for _, _, subject in sorted(accepted, key=lambda s: s[0])]

    def notes_of(self, subject: Subject) -> list[str]:
        return list(self._notes[subject.name])

    def topic_notes(self, subject: Subject, n: int) -> list[str]:
        """Notas de la asignatura cuyo nombre o carpeta indican «tema N» (o unidad, unit...)."""
        pattern = _topic_pattern(n)
        return [p for p in self._notes[subject.name] if pattern.search(norm(p))]
