from __future__ import annotations

from collections.abc import Collection
from pathlib import PurePosixPath


def resolve_note(paths: Collection[str], wanted: str) -> list[str]:
    """Rutas que casan con lo escrito: ruta exacta (con o sin `.md`) o título sin distinguir
    mayúsculas. Devuelve varias si el título está repetido, para que quien llama desambigüe."""
    key = wanted.strip()
    available = set(paths)
    for candidate in (key, f"{key}.md"):
        if candidate in available:
            return [candidate]
    title = key.casefold()
    return sorted(p for p in available if PurePosixPath(p).stem.casefold() == title)
