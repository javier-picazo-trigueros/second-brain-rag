"""Catálogo del índice: asignaturas canónicas, cursos, etiquetas y enlaces de cada nota.

Sirve a los filtros y facetas de la búsqueda y a la resolución de `[[enlaces]]`. Se reconstruye solo
cuando cambia el conjunto de notas del índice (el vault puede cambiar con la API en marcha).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Protocol

from secondbrain.config import Settings
from secondbrain.retrieval.hybrid import canonical_key
from secondbrain.retrieval.subjects import SubjectIndex, SubjectSpec, load_aliases
from secondbrain.store.manifest import Manifest

_COURSE = re.compile(r"^\d+º$")


class NoteMetaSource(Protocol):
    def note_tags(self) -> dict[str, tuple[str, ...]]: ...

    def note_links(self) -> dict[str, tuple[str, ...]]: ...


class Catalog:
    def __init__(
        self,
        settings: Settings,
        manifest: Manifest,
        meta: NoteMetaSource,
        aliases: Mapping[str, SubjectSpec] | None = None,
    ) -> None:
        self._manifest = manifest
        self._meta = meta
        self._aliases = load_aliases(settings.aliases_path) if aliases is None else aliases
        self._key: int | None = None
        self._index: SubjectIndex | None = None
        self._tags: dict[str, tuple[str, ...]] | None = None
        self._paths: set[str] = set()
        self._by_title: dict[str, list[str]] = {}
        self._canonical: dict[str, str] = {}
        self._backlinks: dict[str, list[str]] | None = None

    def _refresh(self) -> SubjectIndex:
        paths = self._manifest.paths()
        key = hash(frozenset(paths))
        if self._index is None or key != self._key:
            self._index = SubjectIndex(paths, self._aliases)
            self._paths = set(paths)
            self._by_title = {}
            for path in sorted(paths):
                self._by_title.setdefault(PurePosixPath(path).stem.casefold(), []).append(path)
            self._canonical = {}
            for group in self._manifest.duplicate_groups():
                rep = min(group, key=canonical_key)
                for member in group:
                    self._canonical[member] = rep
            self._tags = None
            self._backlinks = None
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
            self._tags = self._meta.note_tags()
        return self._tags

    # --- enlaces [[...]] ----------------------------------------------------------------------

    def resolve_link(self, target: str) -> list[str]:
        """Notas a las que apunta `[[target]]`: ruta exacta (con o sin `.md`) o título sin
        distinguir mayúsculas. Las copias exactas cuentan como una (se da la ruta canónica);
        con títulos repetidos devuelve todas las candidatas, para que la interfaz desambigüe."""
        self._refresh()
        key = target.strip()
        found = [c for c in (key, f"{key}.md") if c in self._paths][:1]
        if not found:
            found = self._by_title.get(key.casefold(), [])
        return sorted(dict.fromkeys(self._canonical.get(p, p) for p in found))

    def backlinks(self, path: str) -> list[str]:
        """Notas que enlazan a esta (o a una copia exacta suya), sin ella misma."""
        self._refresh()
        if self._backlinks is None:
            found: dict[str, set[str]] = {}
            for source, targets in self._meta.note_links().items():
                source_rep = self._canonical.get(source, source)
                for target in targets:
                    for destination in self.resolve_link(target):
                        if destination != source_rep:
                            found.setdefault(destination, set()).add(source_rep)
            self._backlinks = {dest: sorted(sources) for dest, sources in found.items()}
        return self._backlinks.get(self._canonical.get(path, path), [])
