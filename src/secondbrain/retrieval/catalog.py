"""Catálogo del índice: asignaturas canónicas, cursos y etiquetas de cada nota.

Sirve a los filtros y facetas de la búsqueda. Se reconstruye solo cuando cambia el conjunto de notas
del índice (el vault puede cambiar mientras la API está en marcha).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

from secondbrain.config import Settings
from secondbrain.retrieval.subjects import SubjectIndex, SubjectSpec, load_aliases
from secondbrain.store.manifest import Manifest

_COURSE = re.compile(r"^\d+º$")


class TagSource(Protocol):
    def note_tags(self) -> dict[str, tuple[str, ...]]: ...


class Catalog:
    def __init__(
        self,
        settings: Settings,
        manifest: Manifest,
        tags: TagSource,
        aliases: Mapping[str, SubjectSpec] | None = None,
    ) -> None:
        self._manifest = manifest
        self._tag_source = tags
        self._aliases = load_aliases(settings.aliases_path) if aliases is None else aliases
        self._key: int | None = None
        self._index: SubjectIndex | None = None
        self._tags: dict[str, tuple[str, ...]] | None = None

    def _refresh(self) -> SubjectIndex:
        paths = self._manifest.paths()
        key = hash(frozenset(paths))
        if self._index is None or key != self._key:
            self._index = SubjectIndex(paths, self._aliases)
            self._tags = None
            self._key = key
        return self._index

    def subject_index(self) -> SubjectIndex:
        return self._refresh()

    def paths(self) -> set[str]:
        return self._manifest.paths()

    def subject_name(self, path: str) -> str | None:
        """Asignatura canónica de la nota (carpeta de asignatura más alias), no el frontmatter."""
        return self._refresh().name_of(path)

    @staticmethod
    def course(path: str) -> str | None:
        first = path.split("/")[0]
        return first if _COURSE.match(first) else None

    def subjects(self) -> list[tuple[str, int]]:
        """(nombre, nº de notas) de las asignaturas que tienen notas, por orden alfabético."""
        index = self._refresh()
        out = [(s.name, len(index.notes_of(s))) for s in index.subjects()]
        return sorted(((n, c) for n, c in out if c > 0), key=lambda item: item[0].casefold())

    def note_tags(self) -> dict[str, tuple[str, ...]]:
        self._refresh()
        if self._tags is None:
            self._tags = self._tag_source.note_tags()
        return self._tags
