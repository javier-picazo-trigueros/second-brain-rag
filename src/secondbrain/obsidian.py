"""Enlaces `obsidian://` para abrir una nota en Obsidian.

Es solo un enlace que construye la API: la aplicación no ejecuta nada ni escribe en el vault; el
navegador (y el sistema operativo) deciden si abren Obsidian.
"""

from __future__ import annotations

from urllib.parse import quote


def obsidian_url(vault: str, note_path: str) -> str:
    """`obsidian://open?vault=<vault>&file=<ruta sin .md>`, con todo codificado."""
    file = note_path.removesuffix(".md")
    return f"obsidian://open?vault={quote(vault, safe='')}&file={quote(file, safe='')}"
