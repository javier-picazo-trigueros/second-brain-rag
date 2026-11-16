from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from secondbrain.ingest.watcher import Debouncer, WatcherService
from tests.env import Env

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
REDES = "3º/REDES/Network layers.md"
NEW_TEXT = "# Condiciones de carrera\n\n" + "contenido nuevo del tema " * 20


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# --- Debouncer ------------------------------------------------------------------------------


def test_debouncer_releases_a_path_after_the_quiet_period() -> None:
    d = Debouncer(1.5)
    d.add("a.md", now=0.0)
    assert d.due(now=1.4) == []
    assert d.due(now=1.5) == ["a.md"]
    assert d.due(now=9.0) == []


def test_new_events_restart_the_quiet_period() -> None:
    d = Debouncer(1.5)
    d.add("a.md", now=0.0)
    d.add("a.md", now=1.0)
    assert d.due(now=2.0) == []
    assert d.due(now=2.5) == ["a.md"]


def test_debouncer_tracks_paths_independently_and_in_order() -> None:
    d = Debouncer(1.0)
    d.add("b.md", now=0.0)
    d.add("a.md", now=0.5)
    assert d.due(now=1.0) == ["b.md"]
    assert d.due(now=1.5) == ["a.md"]


def test_debouncer_returns_sorted_paths_that_fall_due_together() -> None:
    d = Debouncer(1.0)
    for p in ("c.md", "a.md", "b.md"):
        d.add(p, now=0.0)
    assert d.due(now=5.0) == ["a.md", "b.md", "c.md"]


def test_debouncer_exposes_pending_paths() -> None:
    d = Debouncer(1.0)
    d.add("a.md", now=0.0)
    assert d.pending == {"a.md"}


# --- servicio con eventos simulados ---------------------------------------------------------------


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def watcher(env: Env, clock: Clock) -> WatcherService:
    env.indexer().sync()  # el vault ya está indexado, como en un `brain watch` real
    env.embedder.embedded.clear()
    return WatcherService(
        env.indexer(), env.settings(), debounce=1.5, clock=clock, sleep=clock.sleep
    )


def fire(w: WatcherService, clock: Clock, kind: str, src: Path, dest: Path | None = None) -> Any:
    w.handle(kind, src, dest)
    clock.now += 1.5
    return w.process_due()


def test_modified_note_is_reindexed_after_the_debounce(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    env.write(CARRERA, NEW_TEXT)
    watcher.handle("modified", env.vault / CARRERA)
    assert watcher.process_due().indexed == 0  # aún dentro del periodo de calma
    clock.now += 1.5
    report = watcher.process_due()
    assert report.indexed == 1
    assert "contenido nuevo" in env.store.chunks[CARRERA][0].text


def test_a_burst_of_events_indexes_once(env: Env, watcher: WatcherService, clock: Clock) -> None:
    env.write(CARRERA, NEW_TEXT)
    for kind in ("created", "modified", "modified", "modified"):
        watcher.handle(kind, env.vault / CARRERA)
        clock.now += 0.2
    clock.now += 1.5
    assert watcher.process_due().indexed == 1
    assert len(env.embedder.embedded) == len(env.store.chunks[CARRERA])


def test_unchanged_content_is_not_reindexed(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    report = fire(watcher, clock, "modified", env.vault / CARRERA)  # OneDrive "toca" el fichero
    assert (report.indexed, report.unchanged) == (0, 1)
    assert env.embedder.embedded == []


def test_new_note_is_indexed(env: Env, watcher: WatcherService, clock: Clock) -> None:
    env.write("1º/IA/Nueva.md", "# Nueva\n\n" + "texto de la nota nueva " * 20)
    report = fire(watcher, clock, "created", env.vault / "1º/IA/Nueva.md")
    assert report.indexed == 1
    assert "1º/IA/Nueva.md" in env.store.notes


def test_deleted_note_is_removed_from_store_and_manifest(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    (env.vault / CARRERA).unlink()
    report = fire(watcher, clock, "deleted", env.vault / CARRERA)
    assert report.removed == 1
    assert CARRERA not in env.store.notes
    assert CARRERA not in env.manifest.paths()


def test_rename_is_a_delete_plus_an_add(env: Env, watcher: WatcherService, clock: Clock) -> None:
    new = "1º/SISTEMAS OPERATIVOS/Carreras.md"
    (env.vault / CARRERA).rename(env.vault / new)
    report = fire(watcher, clock, "moved", env.vault / CARRERA, env.vault / new)
    assert (report.removed, report.indexed) == (1, 1)
    assert new in env.store.notes and CARRERA not in env.store.notes


def test_atomic_save_through_a_temp_file_reindexes_the_note(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    tmp = env.vault / (CARRERA + ".tmp")
    tmp.write_text(NEW_TEXT, encoding="utf-8", newline="")
    watcher.handle("created", tmp)
    tmp.replace(env.vault / CARRERA)
    watcher.handle("moved", tmp, env.vault / CARRERA)
    clock.now += 1.5
    report = watcher.process_due()
    assert report.indexed == 1
    assert "contenido nuevo" in env.store.chunks[CARRERA][0].text


def test_moving_a_note_into_an_excluded_folder_removes_it(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    dest = env.vault / "_archivo" / "Condiciones de carrera.md"
    (env.vault / CARRERA).replace(dest)
    report = fire(watcher, clock, "moved", env.vault / CARRERA, dest)
    assert (report.removed, report.indexed) == (1, 0)
    assert CARRERA not in env.store.notes


@pytest.mark.parametrize(
    "rel",
    [
        "1º/IA/~$Sin frontmatter.md",
        "1º/IA/Sin frontmatter.md.tmp",
        "1º/IA/borrador.tmp",
        ".obsidian/workspace.md",
        ".git/COMMIT_EDITMSG.md",
        "_conceptos/semaforo.md",
        "_archivo/Nota vieja.md",
        "node_modules/paquete/README.md",
        "1º/IA/imagen.png",
        "convertir.py",
        "CLAUDE.md",
    ],
)
def test_temporary_excluded_and_non_note_files_are_ignored(
    env: Env, watcher: WatcherService, rel: str
) -> None:
    watcher.handle("modified", env.vault / rel)
    assert watcher.pending == set()


def test_paths_matching_exclude_globs_are_ignored(env: Env, clock: Clock) -> None:
    w = WatcherService(
        env.indexer(exclude_globs=["3º/*"]),
        env.settings(exclude_globs=["3º/*"]),
        debounce=1.5,
        clock=clock,
        sleep=clock.sleep,
    )
    w.handle("modified", env.vault / REDES)
    assert w.pending == set()


def test_events_outside_the_vault_are_ignored(
    env: Env, watcher: WatcherService, tmp_path: Path
) -> None:
    watcher.handle("modified", tmp_path / "otro" / "nota.md")
    assert watcher.pending == set()


def test_directory_events_trigger_a_full_resync(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    shutil.move(str(env.vault / "3º" / "REDES"), str(env.vault / "3º" / "NET"))
    watcher.handle("moved", env.vault / "3º" / "REDES", env.vault / "3º" / "NET", is_directory=True)
    clock.now += 1.5
    report = watcher.process_due()
    assert report.resynced is True
    assert (report.removed, report.indexed) == (1, 1)
    assert "3º/NET/Network layers.md" in env.store.notes
    assert REDES not in env.store.notes


def test_nothing_due_returns_an_empty_report(watcher: WatcherService) -> None:
    report = watcher.process_due()
    assert (report.indexed, report.unchanged, report.removed, report.failed) == (0, 0, 0, [])


# --- robustez ---------------------------------------------------------------------------------


def test_locked_files_are_retried_with_backoff(
    env: Env, watcher: WatcherService, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    real = watcher._indexer.index_file

    def flaky(path: Path) -> Any:
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("el archivo está en uso por OneDrive")
        return real(path)

    monkeypatch.setattr(watcher._indexer, "index_file", flaky)
    env.write(CARRERA, NEW_TEXT)
    report = fire(watcher, clock, "modified", env.vault / CARRERA)
    assert report.indexed == 1 and report.failed == []
    assert calls["n"] == 3
    assert clock.sleeps == [0.5, 1.0]


def test_a_file_that_stays_locked_is_reported_not_raised(
    env: Env, watcher: WatcherService, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(path: Path) -> Any:
        raise PermissionError("bloqueado")

    monkeypatch.setattr(watcher._indexer, "index_file", locked)
    report = fire(watcher, clock, "modified", env.vault / CARRERA)
    assert [p for p, _ in report.failed] == [CARRERA]
    assert "bloqueado" in report.failed[0][1]
    assert len(clock.sleeps) == 2  # 3 intentos, 2 esperas


def test_an_indexing_error_does_not_stop_the_other_notes(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    env.write(CARRERA, NEW_TEXT)
    env.write("1º/IA/Nueva.md", "# Nueva\n\n" + "texto de la nota nueva " * 20)
    env.embedder.fail_on = "contenido nuevo"
    watcher.handle("modified", env.vault / CARRERA)
    watcher.handle("created", env.vault / "1º/IA/Nueva.md")
    clock.now += 1.5
    report = watcher.process_due()
    assert [p for p, _ in report.failed] == [CARRERA]
    assert report.indexed == 1


def test_a_note_deleted_before_processing_is_removed_without_error(
    env: Env, watcher: WatcherService, clock: Clock
) -> None:
    watcher.handle("modified", env.vault / CARRERA)
    (env.vault / CARRERA).unlink()
    clock.now += 1.5
    report = watcher.process_due()
    assert (report.removed, report.failed) == (1, [])


# --- watchdog real (sin Ollama ni Qdrant: fakes) ---------------------------------


def _wait(condition: Callable[[], bool], timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def test_real_filesystem_events_reach_the_index(env: Env) -> None:
    env.indexer().sync()
    service = WatcherService(env.indexer(), env.settings(), debounce=0.3)
    stop = threading.Event()
    thread = threading.Thread(target=service.run, args=(stop,), daemon=True)
    thread.start()
    try:
        time.sleep(0.5)  # deja arrancar el observador
        env.write("1º/IA/Nueva en vivo.md", "# Nueva\n\n" + "texto escrito en vivo " * 20)
        assert _wait(lambda: "1º/IA/Nueva en vivo.md" in env.store.notes)
        (env.vault / "1º/IA/Nueva en vivo.md").unlink()
        assert _wait(lambda: "1º/IA/Nueva en vivo.md" not in env.store.notes)
    finally:
        stop.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
