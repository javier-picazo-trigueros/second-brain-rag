from __future__ import annotations

import hashlib
import re
import unicodedata

PLACEHOLDER = re.compile(r"^\*\(sin texto extraíble[^\n]*\)\*[ \t]*$", re.M)
# Marcadores de página de los apuntes convertidos desde PDF ("## Página 3"): no son contenido.
PAGE_MARKER = re.compile(r"^#{1,6}[ \t]+p[aá]gina\s+\d+[ \t]*$", re.I | re.M)

# Por debajo de este tamaño no se huella: las notas casi vacías no son "copias" entre sí.
_MIN_HASH_CHARS = 200


def body_fingerprint(body: str) -> str | None:
    """Hash del cuerpo normalizado (sin placeholders ni marcadores de página, NFC, sin espacios).

    Dos notas con el mismo valor tienen el mismo texto aunque difiera su frontmatter.
    """
    text = unicodedata.normalize("NFC", PAGE_MARKER.sub("", PLACEHOLDER.sub("", body)))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < _MIN_HASH_CHARS:
        return None
    return hashlib.sha256(text.encode()).hexdigest()
