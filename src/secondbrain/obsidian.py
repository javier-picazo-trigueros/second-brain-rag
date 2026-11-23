"""Enlaces `obsidian://` para abrir una nota en Obsidian.

Es solo un enlace que construye la API: la aplicación no ejecuta nada ni escribe en el vault; el
navegador (y el sistema operativo) deciden si abren Obsidian.
"""

from __future__ import annotations

from urllib.parse import quote

from secondbrain.config import Settings


def obsidian_url(vault: str, note_path: str) -> str:
    """`obsidian://open?vault=<vault>&file=<ruta sin .md>`, con todo codificado."""
    file = note_path.removesuffix(".md")
    return f"obsidian://open?vault={quote(vault, safe='')}&file={quote(file, safe='')}"


def obsidian_path_url(absolute_path: str) -> str:
    """`obsidian://open?path=<ruta absoluta del archivo>`: no depende del nombre del vault."""
    return f"obsidian://open?path={quote(absolute_path.replace(chr(92), '/'), safe='')}"


def obsidian_link(settings: Settings, note_path: str) -> str:
    """Enlace para abrir una nota. Por ruta absoluta salvo que se haya configurado el nombre del
    vault (`BRAIN_OBSIDIAN_VAULT`), que es la alternativa para quien lo tenga registrado así."""
    if settings.obsidian_vault:
        return obsidian_url(settings.obsidian_vault, note_path)
    return obsidian_path_url((settings.vault_path.resolve() / note_path).as_posix())
