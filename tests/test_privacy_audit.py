"""Auditoría de privacidad: rutas y títulos del vault real, datos personales y autoría."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from secondbrain.privacy_audit import (
    Finding,
    Markers,
    audit_message,
    audit_repository,
    audit_text,
    load_markers,
    main,
)

REAL = "3º/Asignatura Inventada/Tema 7 Apuntes de ejemplo largo.md"
EMAIL = "autor@users.noreply.github.com"
# Se componen en ejecución para que el propio repositorio no contenga datos con aspecto personal.
WIN_USER = "C:" + chr(92) + "Users" + chr(92) + "persona" + chr(92) + "Documents"
MAIL = "alguien" + "@" + "gmail.com"
TOKEN = "gh" + "p_" + "abcdefghijklmnopqrstuvwx"
KEY = "-----BEGIN RSA " + "PRIVATE KEY-----"


def markers(*paths: str, fixtures: tuple[str, ...] = ()) -> Markers:
    return Markers.from_paths(paths, fixture_paths=fixtures)


def kinds(findings: list[Finding]) -> list[str]:
    return sorted(f.kind for f in findings)


# --- rutas y títulos ------------------------------------------------------------------------


def test_a_full_real_path_is_reported() -> None:
    found = audit_text(f'ruta = "{REAL}"', "a.py", markers(REAL))
    assert "ruta" in kinds(found)


def test_path_match_ignores_case_backslashes_and_url_encoding() -> None:
    m = markers(REAL)
    assert audit_text(REAL.upper(), "a.py", m)
    assert audit_text(REAL.replace("/", "\\\\"), "a.py", m)
    assert audit_text(REAL.replace("/", "%2F").replace(" ", "%20"), "a.py", m)


def test_a_distinctive_title_is_reported_on_its_own() -> None:
    found = audit_text("Resumen de Tema 7 Apuntes de ejemplo largo", "a.md", markers(REAL))
    assert kinds(found) == ["título"]


@pytest.mark.parametrize(
    "path", ["2º/DIS/README.md", "1º/IA/license.md", "3º/IA II/IA II.md", "x/Tema 1.md"]
)
def test_generic_or_short_titles_are_not_reported(path: str) -> None:
    text = "README license IA II Tema 1 licencia readme"
    assert not audit_text(text, "a.md", markers(path))


def test_fixture_notes_are_not_reported_even_if_the_real_vault_has_the_same_name() -> None:
    shared = "1º/IA/Condiciones de carrera con hilos.md"
    m = markers(shared, fixtures=(shared,))
    assert not audit_text("Condiciones de carrera con hilos", "a.md", m)


def test_files_inside_the_fixture_vault_are_never_scanned() -> None:
    assert not audit_text(REAL, "tests/fixtures/vault/x.md", markers(REAL))


# --- datos personales -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        f"vault = {WIN_USER}",
        "ruta /home/" + "persona/notas",
        f"contacto: {MAIL}",
        f"token {TOKEN}",
        KEY,
    ],
)
def test_personal_data_is_reported(line: str) -> None:
    assert kinds(audit_text(line, "a.md", markers())) == ["personal"]


@pytest.mark.parametrize(
    "line",
    [
        r"vault = C:\ruta\a\tu\vault",
        f"Author {EMAIL}",
        "usuario@example.org",
        "decorador @dataclass y @app.command()",
        r"ejemplo C:\\Users\\yo y tú\\Cerebro y /home/user/notas",
    ],
)
def test_generic_examples_are_not_personal_data(line: str) -> None:
    assert not audit_text(line, "a.md", markers())


def test_short_prose_like_titles_are_not_reported() -> None:
    assert not audit_text("Sistemas: apuntes de C", "a.md", markers("2º/SO/Apuntes de C.md"))


# --- mensajes de commit ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "feat: algo\n\nCo-Authored-By: alguien <a@b.c>",
        "feat: hecho con Claude",
        "docs: generado con ChatGPT",
        "fix: Generated with una herramienta",
        "fix: usar openai",
    ],
)
def test_ai_mentions_in_commit_messages_are_reported(message: str) -> None:
    assert kinds(audit_message(message)) == ["ia"]


@pytest.mark.parametrize(
    "message",
    ["feat: IA II con README y license", "docs: apuntes de IA I", "fix: copia de CLAUDE.md"],
)
def test_subject_names_and_the_project_file_are_not_ai_mentions(message: str) -> None:
    assert not audit_message(message)


# --- repositorio ----------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return out.stdout


def commit(repo: Path, name: str, text: str, message: str, email: str = EMAIL) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(
        repo,
        "-c",
        f"user.email={email}",
        "-c",
        "user.name=a",
        "commit",
        "-q",
        "-m",
        message,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", EMAIL)
    git(path, "config", "user.name", "a")
    return path


def test_added_lines_in_unpublished_commits_are_audited(repo: Path) -> None:
    commit(repo, "a.py", "x = 1\n", "feat: base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit(repo, "b.py", f'RUTA = "{REAL}"\n', "test: ejemplo")
    found = audit_repository(repo, "HEAD", markers(REAL), EMAIL)
    assert ("ruta" in kinds(found)) and any("b.py" in f.where for f in found)


def test_a_published_path_is_reported_only_while_it_is_in_the_tree(repo: Path) -> None:
    commit(repo, "a.py", f'RUTA = "{REAL}"\n', "test: ya publicado")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert kinds(audit_repository(repo, "HEAD", markers(REAL), EMAIL)) == ["ruta"]
    commit(repo, "a.py", 'RUTA = "3º/Ejemplo/Nota ficticia.md"\n', "test: ejemplo ficticio")
    assert audit_repository(repo, "HEAD", markers(REAL), EMAIL) == []


def test_commit_author_must_be_the_configured_one(repo: Path) -> None:
    commit(repo, "a.py", "x = 1\n", "feat: base", email=MAIL)
    found = audit_repository(repo, "HEAD", markers(), EMAIL)
    assert "autoría" in kinds(found)


def test_ai_mention_in_an_unpublished_commit_message_is_reported(repo: Path) -> None:
    commit(repo, "a.py", "x = 1\n", "feat: hecho con Claude")
    assert "ia" in kinds(audit_repository(repo, "HEAD", markers(), EMAIL))


# --- manifest y línea de órdenes ------------------------------------------------------------


def make_manifest(path: Path, *notes: str) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE notes (path TEXT PRIMARY KEY)")
    db.executemany("INSERT INTO notes VALUES (?)", [(n,) for n in notes])
    db.commit()
    db.close()
    return path


def test_load_markers_reads_the_manifest(tmp_path: Path) -> None:
    manifest = make_manifest(tmp_path / "m.sqlite", REAL)
    loaded = load_markers(manifest, fixtures_dir=None)
    assert loaded is not None and audit_text(REAL, "a.md", loaded)


def test_load_markers_returns_none_without_a_manifest(tmp_path: Path) -> None:
    assert load_markers(tmp_path / "no-existe.sqlite", fixtures_dir=None) is None


def test_main_fails_with_findings_and_passes_when_clean(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = make_manifest(tmp_path / "m.sqlite", REAL)
    commit(repo, "a.py", f'RUTA = "{REAL}"\n', "test: con ruta real")
    args = ["--repo", str(repo), "--manifest", str(manifest), "--email", EMAIL]
    assert main(args) == 1
    assert "ruta" in capsys.readouterr().out
    commit(repo, "a.py", "RUTA = 1\n", "test: limpio")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert main(args) == 0


def test_main_without_a_manifest_skips_only_the_vault_checks(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(repo, "a.py", f'RUTA = "{REAL}"\n', "test: sin manifest")
    args = ["--repo", str(repo), "--manifest", str(tmp_path / "no.sqlite"), "--email", EMAIL]
    assert main(args) == 0
    assert "omitidas" in capsys.readouterr().out
    commit(repo, "b.md", f"correo {MAIL}\n", "docs: con correo")
    assert main(args) == 1
