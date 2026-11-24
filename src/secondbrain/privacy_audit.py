"""Auditoría de privacidad antes de publicar.

Comprueba, en los commits que aún no están en ningún remoto y en el árbol que se va a publicar:

- rutas completas y títulos distintivos de las notas del vault real (leídos del manifest),
- datos personales (rutas de usuario, correos, credenciales),
- autoría (todos los commits a nombre del correo configurado) y menciones a una IA en los mensajes.

Sin manifest se omiten solo las comprobaciones del vault. Código de salida 1 si hay hallazgos.
Uso: ``python -m secondbrain.privacy_audit [--tip REV]``.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from pydantic import ValidationError

from secondbrain.config import load_settings

FIXTURES_PREFIX = "tests/fixtures/vault/"
_MIN_TITLE_LEN = 14
# Palabras sueltas que aparecen como título de nota pero también en el código y la documentación.
_GENERIC_TITLES = frozenset({"introduction", "introducción", "resumen general", "apuntes"})
_PERSONAL = re.compile(
    r"(?i)(?:[a-z]:[/\\]+(?:users|usuarios)[/\\]+[^/\\\s'\"`<>]+"
    r"|/home/[\w.-]+"
    r"|(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b"
    r"|gh[pousr]_[a-z0-9]{18,}|github_pat_\w+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
# Nombres de usuario de ejemplo: `C:\Users\yo`, `/home/user`.
_PLACEHOLDER_USERS = frozenset({"yo", "user", "usuario", "you", "tu", "tú", "name", "nombre"})
_USER_PATH = re.compile(r"(?i)(?:users|usuarios|home)[/\\]+([^/\\\s'\"`<>]+)")
_ALLOWED_EMAIL_DOMAINS = ("users.noreply.github.com", "example.org", "example.com", "example.net")
_AI_MENTION = re.compile(
    r"(?i)\b(?:claude|anthropic|codex|chatgpt|openai|copilot|gemini"
    r"|co-authored-by|generated with)\b"
)
_PROJECT_FILE = re.compile(r"(?i)CLAUDE\.md")


@dataclass(frozen=True, order=True)
class Finding:
    kind: str  # ruta | título | personal | autoría | ia
    where: str
    value: str


def _fold(text: str) -> str:
    """Minúsculas, NFC, separadores `/` y URL decodificada: así se compara la ruta escrita de
    cualquier modo (JSON con `\\\\`, enlaces con `%20`, mayúsculas)."""
    unescaped = unquote(text).replace("\\\\", "/").replace("\\", "/")
    return unicodedata.normalize("NFC", unescaped).casefold()


def _alternation(values: Iterable[str]) -> re.Pattern[str] | None:
    ordered = sorted(set(values), key=len, reverse=True)
    return re.compile("|".join(re.escape(v) for v in ordered)) if ordered else None


def _is_distinctive(stem: str) -> bool:
    return (
        len(stem) >= _MIN_TITLE_LEN
        and stem not in _GENERIC_TITLES
        and any(c == " " or c == "-" or c.isdigit() for c in stem)
    )


class Markers:
    """Rutas completas y títulos distintivos del vault real."""

    def __init__(self, paths: re.Pattern[str] | None, titles: re.Pattern[str] | None) -> None:
        self._paths = paths
        self._titles = titles

    @classmethod
    def from_paths(cls, paths: Iterable[str], fixture_paths: Iterable[str] = ()) -> Markers:
        fixtures = {_fold(p) for p in fixture_paths}
        real = {_fold(p) for p in paths} - fixtures
        fixture_stems = {Path(p).stem for p in fixtures}
        stems = {Path(p).stem for p in real if _is_distinctive(Path(p).stem)} - fixture_stems
        return cls(_alternation(real), _alternation(stems))

    def find(self, folded: str) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if self._paths is not None:
            found += [("ruta", m) for m in self._paths.findall(folded)]
            folded = self._paths.sub(" ", folded)  # un título dentro de una ruta ya se contó
        if self._titles is not None:
            found += [("título", m) for m in self._titles.findall(folded)]
        return found


def _personal(text: str) -> Iterable[str]:
    for match in _PERSONAL.findall(text):
        if "@" in match and match.casefold().endswith(_ALLOWED_EMAIL_DOMAINS):
            continue
        user = _USER_PATH.search(match)
        if user is not None and user.group(1).casefold() in _PLACEHOLDER_USERS:
            continue
        yield match


def audit_text(text: str, where: str, markers: Markers | None) -> list[Finding]:
    """Datos personales y, si hay `markers`, rutas y títulos del vault. `where` es el fichero."""
    findings: set[Finding] = set()
    for line in text.splitlines():
        findings.update(Finding("personal", where, p) for p in _personal(line))
        if markers is not None and FIXTURES_PREFIX not in where:
            findings.update(Finding(kind, where, v) for kind, v in markers.find(_fold(line)))
    return sorted(findings)


def audit_message(message: str) -> list[Finding]:
    """Menciones a una IA y trailers de coautoría en un mensaje de commit."""
    cleaned = _PROJECT_FILE.sub("", message)
    return [Finding("ia", "mensaje", m) for m in sorted(set(_AI_MENTION.findall(cleaned)))]


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _audit_diff(diff: str, label: str, markers: Markers | None) -> list[Finding]:
    findings: list[Finding] = []
    file = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            file = line[6:] if line.startswith("+++ b/") else ""
            if file:
                findings += audit_text(file, f"{label}:{file}", markers)
        elif line.startswith("+") and file:
            findings += audit_text(line[1:], f"{label}:{file}", markers)
    return findings


def audit_repository(
    repo: Path, tip: str, markers: Markers | None, expected_email: str | None
) -> list[Finding]:
    """Commits de `tip` que no están en ningún remoto, más el árbol completo de `tip`."""
    findings: list[Finding] = []
    commits = _text(_git(repo, "rev-list", tip, "--not", "--remotes=origin")).split()
    for sha in commits:
        label = sha[:7]
        message = _text(_git(repo, "show", "-s", "--format=%B", sha))
        findings += [Finding(f.kind, f"{label}:mensaje", f.value) for f in audit_message(message)]
        emails = _text(_git(repo, "show", "-s", "--format=%ae%n%ce", sha)).split()
        if expected_email is not None:
            findings += [Finding("autoría", label, e) for e in emails if e != expected_email]
        diff = _text(_git(repo, "show", "--format=", "-U0", "--no-renames", sha))
        findings += _audit_diff(diff, label, markers)
    names = _git(repo, "ls-tree", "-r", "--name-only", "-z", tip).split(b"\0")
    for raw_name in filter(None, names):
        name = _text(raw_name)
        content = _git(repo, "show", f"{tip}:{name}")
        if b"\0" not in content:
            findings += audit_text(_text(content), f"{tip[:7]}:{name}", markers)
            findings += audit_text(name, f"{tip[:7]}:{name}", markers)
    return sorted(set(findings))


def load_markers(manifest_path: Path, fixtures_dir: Path | None) -> Markers | None:
    """Rutas del manifest (solo lectura), o None si no hay manifest."""
    if not manifest_path.exists():
        return None
    with closing(sqlite3.connect(manifest_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        paths = [str(row[0]) for row in db.execute("SELECT path FROM notes")]
    fixtures = (
        [p.relative_to(fixtures_dir).as_posix() for p in fixtures_dir.rglob("*.md")]
        if fixtures_dir is not None and fixtures_dir.exists()
        else []
    )
    return Markers.from_paths(paths, fixture_paths=fixtures)


def _default_manifest(repo: Path) -> Path:
    """Manifest de la configuración local o, sin ella (integración continua), `data/` del repo."""
    try:
        return load_settings().manifest_path
    except ValidationError:
        return repo / "data" / "manifest.sqlite"


def _local_email(repo: Path) -> str | None:
    try:
        return _text(_git(repo, "config", "--local", "user.email")).strip() or None
    except subprocess.CalledProcessError:
        return None


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditoría de privacidad previa a la publicación")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--tip", default="HEAD", help="commit que se va a publicar")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--email", default=None, help="correo esperado de autor y committer")
    args = parser.parse_args(argv)
    repo: Path = args.repo
    manifest: Path = args.manifest if args.manifest is not None else _default_manifest(repo)
    email = args.email or _local_email(repo)
    if email is None:
        _say("Comprobación de autoría omitida: no hay correo local configurado en el repositorio.")
    markers = load_markers(manifest, repo / FIXTURES_PREFIX)
    if markers is None:
        _say(f"Comprobaciones de rutas y títulos omitidas: no hay manifest en {manifest}.")
    findings = audit_repository(repo, args.tip, markers, email)
    for f in findings:
        _say(f"{f.kind:9} {f.where}  {f.value}")
    _say(f"Auditoría: {len(findings)} hallazgos.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
