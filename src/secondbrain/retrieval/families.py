"""Familias de copias: las copias exactas y las versiones de una misma nota cuentan como una.

Dos notas son **copias exactas** si tienen el mismo cuerpo (lo decide el manifiesto, también entre
asignaturas). Son **versiones** si, dentro de la misma asignatura canónica, sus títulos solo se
distinguen por un sufijo « (n)» o «copia»/«copy», aunque el contenido no coincida byte a byte
(«DM - Unit 5 - Classification» y «DM - Unit 5 - Classification (1)»). Ambas relaciones se unen en
una sola familia, de la que se muestra una representante: la de título sin sufijo y, si no la hay,
la de más fragmentos.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath

from secondbrain.config import Settings
from secondbrain.retrieval.subjects import SubjectIndex, SubjectSpec, load_aliases
from secondbrain.store.manifest import Manifest

# Sufijos de copia: « (1)», « - copia», « copy (2)». Solo 1-2 dígitos: «(2024)» no es una copia.
_SUFFIX = re.compile(r"\s*(\(\d{1,2}\)|[-_ ]*(?:copia|copy)(?:\s*\(\d{1,2}\))?)\s*$", re.I)
_SPACES = re.compile(r"\s+")


def base_title(stem: str) -> str:
    """Título sin los sufijos de copia, en minúsculas y con los espacios normalizados."""
    previous = None
    while previous != stem:
        previous, stem = stem, _SUFFIX.sub("", stem)
    return _SPACES.sub(" ", stem).strip().casefold()


def has_version_suffix(stem: str) -> bool:
    return _SUFFIX.search(stem) is not None


SubjectOf = Callable[[str], str | None]


class CopyFamilies:
    def __init__(
        self,
        manifest: Manifest,
        subject_of: SubjectOf | None = None,
        *,
        on_paths: Callable[[set[str]], None] | None = None,
    ) -> None:
        """`subject_of`: asignatura canónica de una ruta; sin ella solo hay copias exactas.
        `on_paths` se avisa cuando cambia el conjunto de notas, para refrescar `subject_of`."""
        self._manifest = manifest
        self._subject_of = subject_of
        self._on_paths = on_paths
        self._key: tuple[int, tuple[tuple[str, ...], ...]] | None = None
        self._groups: list[tuple[str, ...]] = []

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        manifest: Manifest,
        aliases: Mapping[str, SubjectSpec] | None = None,
    ) -> CopyFamilies:
        table = load_aliases(settings.aliases_path) if aliases is None else aliases
        index: list[SubjectIndex] = []

        def refresh(paths: set[str]) -> None:
            index[:] = [SubjectIndex(paths, table)]

        def subject_of(path: str) -> str | None:
            return index[0].name_of(path) if index else None

        return cls(manifest, subject_of, on_paths=refresh)

    # --- consulta -----------------------------------------------------------------------------

    def groups(self) -> list[tuple[str, ...]]:
        """Familias de dos o más notas, ordenadas."""
        exact = self._manifest.duplicate_groups()
        paths = self._manifest.paths()
        key = (hash(frozenset(paths)), tuple(exact))
        if key != self._key:
            if self._on_paths is not None:
                self._on_paths(paths)
            self._groups = self._build(paths, exact)
            self._key = key
        return self._groups

    def representative(self, members: Iterable[str]) -> str:
        """La nota que da la cara por la familia: sin sufijo, luego la de más fragmentos."""
        counts = self._manifest.chunk_counts()
        return min(
            members,
            key=lambda p: (
                has_version_suffix(PurePosixPath(p).stem),
                -counts.get(p, 0),
                len(p),
                p,
            ),
        )

    def index(self) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
        """Para cada nota de una familia: su representante; y, por representante, las demás."""
        canonical: dict[str, str] = {}
        others: dict[str, tuple[str, ...]] = {}
        for group in self.groups():
            rep = self.representative(group)
            others[rep] = tuple(p for p in group if p != rep)
            for path in group:
                canonical[path] = rep
        return canonical, others

    # --- construcción -------------------------------------------------------------------------

    def _build(self, paths: set[str], exact: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
        parent: dict[str, str] = {}

        def find(p: str) -> str:
            parent.setdefault(p, p)
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        def union(a: str, b: str) -> None:
            parent[find(a)] = find(b)

        for group in exact:
            for other in group[1:]:
                union(group[0], other)

        if self._subject_of is not None:
            versions: dict[tuple[str, str], list[str]] = {}
            for path in sorted(paths):
                subject = self._subject_of(path)
                if subject is not None:
                    key = (subject, base_title(PurePosixPath(path).stem))
                    versions.setdefault(key, []).append(path)
            for members in versions.values():
                for linked in self._linked_versions(members, find):
                    for other in linked[1:]:
                        union(linked[0], other)

        families: dict[str, list[str]] = {}
        for path in list(parent):
            families.setdefault(find(path), []).append(path)
        return sorted(tuple(sorted(v)) for v in families.values() if len(v) > 1)

    @staticmethod
    def _linked_versions(members: list[str], find: Callable[[str], str]) -> list[list[str]]:
        """Qué notas de un mismo (asignatura, título base) son versiones unas de otras.

        Las versiones se unen a la nota sin sufijo solo si esa es la única (varios «README.md» son
        notas distintas, no copias; dos originales que son copias exactas cuentan como uno).
        Sin original, solo se unen las de una misma carpeta.
        """
        plain = [p for p in members if not has_version_suffix(PurePosixPath(p).stem)]
        versions = [p for p in members if p not in plain]
        if not versions:
            return []
        if plain:
            single = len({find(p) for p in plain}) == 1
            return [[plain[0], *versions]] if single else []
        by_folder: dict[str, list[str]] = {}
        for path in versions:
            by_folder.setdefault(str(PurePosixPath(path).parent), []).append(path)
        return [group for group in by_folder.values() if len(group) > 1]
