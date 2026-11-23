"""Apuntes generados: la ÚNICA escritura que se permite en el vault.

Todo lo demás del vault es de solo lectura. Aquí solo se crea un fichero nuevo, de extensión `.md`,
directamente dentro de `_generadas/`: nunca se sobrescribe (si existe se añade « (2)», « (3)»…), la
ruta se valida contra salidas de la carpeta y el índice no lee esa carpeta. Guardar exige que la
interfaz haya enseñado antes la vista previa y el usuario la haya confirmado.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import yaml

from secondbrain.config import Settings

log = logging.getLogger(__name__)

GENERATED_DIR = "_generadas"
MAX_BYTES = 500_000
_NAME_MAX = 80
_UNSAFE = re.compile(r"[\\/:*?\"<>|\[\]#^.\x00-\x1f]")
_SPACES = re.compile(r"\s+")
_CITATION = re.compile(r"[ \t]?\[S\d{1,3}\]")
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10))} | {
    f"LPT{i}" for i in range(1, 10)
})  # fmt: skip
_WIKILINK_FORBIDDEN = re.compile(r"[\[\]#^|\n\r]")
_VALID_PATH = re.compile(rf"^{GENERATED_DIR}/[^/\\\x00-\x1f]+\.md$")
_MAX_COPIES = 1000


class GeneratedError(ValueError):
    """Ruta o contenido que no se puede guardar; el mensaje es apto para mostrarse."""


@dataclass(frozen=True, slots=True)
class GeneratedPreview:
    path: str  # relativa al vault: lo que se escribiría
    content: str


def safe_name(title: str) -> str:
    """Nombre de fichero (sin extensión) seguro en Windows, macOS y Linux a partir de un título."""
    name = _SPACES.sub(" ", _UNSAFE.sub(" ", title)).strip(" .")
    name = name[:_NAME_MAX].strip(" .")
    if not name:
        return "Apuntes"
    return f"{name} apuntes" if name.upper() in _RESERVED else name


def _one_line(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def source_link(path: str) -> str:
    """`[[Título]]` si Obsidian lo admite; si el título lleva `[ ] # ^ |`, un enlace Markdown."""
    title = PurePosixPath(path).stem
    if not _WIKILINK_FORBIDDEN.search(title):
        return f"[[{title}]]"
    escaped = re.sub(r"([\\\[\]])", r"\\\1", _one_line(title))
    return f"[{escaped}]({quote(_one_line(path), safe='/')})"


def build_note(
    *,
    title: str,
    markdown: str,
    asignatura: str | None,
    tema: int | None,
    sources: list[str],
    today: date | None = None,
) -> str:
    """Nota completa: frontmatter (asignatura, tema, fecha, fuentes), apuntes y lista de fuentes."""
    links = list(dict.fromkeys(source_link(p) for p in sources))
    meta: dict[str, object] = {"titulo": _one_line(title)}
    if asignatura:
        meta["asignatura"] = _one_line(asignatura)
    if tema is not None:
        meta["tema"] = tema
    meta["fecha"] = (today or date.today()).isoformat()
    meta["generada"] = True
    meta["fuentes"] = links
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False)
    body = _CITATION.sub("", markdown).strip()
    sources_block = "\n".join(f"- {link}" for link in links)
    parts = [f"---\n{head.rstrip()}\n---\n", body]
    if links:
        parts.append(f"## Fuentes\n\n{sources_block}")
    return "\n\n".join(parts).rstrip() + "\n"


def _generated_dir(settings: Settings, *, create: bool) -> Path:
    vault = settings.vault_path
    if not vault.is_dir():
        raise GeneratedError("La carpeta del vault no existe: no se puede guardar.")
    target = vault / GENERATED_DIR
    if target.exists() or target.is_symlink():
        if target.resolve() != vault.resolve() / GENERATED_DIR or not target.is_dir():
            raise GeneratedError(f"«{GENERATED_DIR}» no es una carpeta normal dentro del vault.")
    elif create:
        target.mkdir()
    return target


def _free_name(folder: Path, name: str) -> str:
    if not (folder / f"{name}.md").exists():
        return name
    for n in range(2, _MAX_COPIES):
        if not (folder / f"{name} ({n}).md").exists():
            return f"{name} ({n})"
    raise GeneratedError("Hay demasiadas copias con ese nombre.")


def preview(settings: Settings, title: str, content: str) -> GeneratedPreview:
    """Dónde se guardaría y qué se escribiría. No toca el disco."""
    folder = _generated_dir(settings, create=False)
    name = _free_name(folder, safe_name(title)) if folder.exists() else safe_name(title)
    return GeneratedPreview(f"{GENERATED_DIR}/{name}.md", content)


def _check_path(path: str) -> str:
    if not _VALID_PATH.match(path) or ".." in PurePosixPath(path).parts:
        raise GeneratedError(f"Solo se puede guardar un .md directamente en «{GENERATED_DIR}/».")
    return PurePosixPath(path).name.removesuffix(".md")


def save(settings: Settings, path: str, content: str) -> str:
    """Crea el fichero (nunca sobrescribe) y devuelve la ruta final, relativa al vault."""
    name = _check_path(path)
    if not content.strip():
        raise GeneratedError("No hay nada que guardar.")
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise GeneratedError("Los apuntes son demasiado largos para guardarlos.")
    folder = _generated_dir(settings, create=True)
    for n in range(1, _MAX_COPIES):
        candidate = name if n == 1 else f"{name} ({n})"
        try:
            # «x»: falla si existe, también si alguien lo crea entre la comprobación y la escritura.
            with open(folder / f"{candidate}.md", "x", encoding="utf-8", newline="\n") as out:
                out.write(content)
        except FileExistsError:
            continue
        log.info("Apuntes guardados en %s/%s.md", GENERATED_DIR, candidate)
        return f"{GENERATED_DIR}/{candidate}.md"
    raise GeneratedError("Hay demasiadas copias con ese nombre.")
