from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from secondbrain.api.reindex import AlreadyRunning, ReindexManager
from secondbrain.ingest.indexer import SyncReport

Progress = Callable[[int, int, str], None] | None


def finished_report() -> SyncReport:
    return SyncReport(indexed=2, unchanged=8)


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    done = threading.Event()

    def poll() -> None:
        while not done.is_set() and not condition():
            done.wait(0.01)

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    thread.join(timeout)
    done.set()
    return condition()


def test_it_starts_idle() -> None:
    status = ReindexManager(lambda progress: finished_report()).status()
    assert status.state == "idle"
    assert (status.done, status.total, status.report) == (0, 0, None)


def test_a_run_goes_running_then_done_with_its_report() -> None:
    release = threading.Event()

    def run(progress: Progress) -> SyncReport:
        assert progress is not None
        progress(1, 3, "a.md")
        release.wait(5)
        progress(3, 3, "c.md")
        return finished_report()

    manager = ReindexManager(run)
    manager.start()
    assert wait_until(lambda: manager.status().done == 1)
    running = manager.status()
    assert (running.state, running.total, running.current) == ("running", 3, "a.md")
    release.set()
    assert wait_until(lambda: manager.status().state == "done")
    done = manager.status()
    assert (done.done, done.report) == (3, finished_report())
    assert done.finished_at is not None and done.started_at is not None


def test_only_one_run_at_a_time() -> None:
    release = threading.Event()
    manager = ReindexManager(lambda progress: (release.wait(5), finished_report())[1])
    manager.start()
    with pytest.raises(AlreadyRunning):
        manager.start()
    release.set()
    assert wait_until(lambda: manager.status().state == "done")


def test_it_can_run_again_after_finishing() -> None:
    manager = ReindexManager(lambda progress: finished_report())
    manager.start()
    assert wait_until(lambda: manager.status().state == "done")
    manager.start()
    assert wait_until(lambda: manager.status().state == "done")


def test_a_failing_run_is_reported_without_raising() -> None:
    def boom(progress: Progress) -> SyncReport:
        raise RuntimeError("Qdrant no responde")

    manager = ReindexManager(boom)
    manager.start()
    assert wait_until(lambda: manager.status().state == "error")
    status = manager.status()
    assert status.error is not None and "Qdrant no responde" in status.error
    manager.start()  # tras un error se puede reintentar
    assert wait_until(lambda: manager.status().state == "error")


def test_starting_resets_the_previous_progress() -> None:
    manager = ReindexManager(lambda progress: finished_report())
    manager.start()
    assert wait_until(lambda: manager.status().state == "done")
    release = threading.Event()
    manager2 = ReindexManager(lambda progress: (release.wait(5), finished_report())[1])
    manager2.start()
    status = manager2.status()
    assert (status.done, status.total, status.report) == (0, 0, None)
    release.set()
    assert wait_until(lambda: manager2.status().state == "done")
