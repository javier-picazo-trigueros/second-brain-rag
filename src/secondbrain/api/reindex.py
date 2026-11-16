from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from secondbrain.ingest.indexer import SyncReport

log = logging.getLogger(__name__)

Progress = Callable[[int, int, str], None]


class AlreadyRunning(RuntimeError):
    """Ya hay un reindexado en marcha."""


@dataclass(frozen=True, slots=True)
class ReindexStatus:
    state: str = "idle"  # idle | running | done | error
    done: int = 0
    total: int = 0
    current: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    report: SyncReport | None = None
    error: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ReindexManager:
    """Lanza `sync` en un hilo, de una vez en una, y deja consultar su progreso."""

    def __init__(self, run: Callable[[Progress], SyncReport]) -> None:
        self._run = run
        self._status = ReindexStatus()
        self._lock = threading.Lock()

    def status(self) -> ReindexStatus:
        with self._lock:
            return self._status

    def start(self) -> None:
        with self._lock:
            if self._status.state == "running":
                raise AlreadyRunning("Ya hay un reindexado en marcha.")
            self._status = ReindexStatus(state="running", started_at=_now())
        threading.Thread(target=self._work, name="reindex", daemon=True).start()

    def _progress(self, done: int, total: int, current: str) -> None:
        with self._lock:
            self._status = replace(self._status, done=done, total=total, current=current)

    def _work(self) -> None:
        try:
            report = self._run(self._progress)
        except Exception as exc:  # el fallo se guarda en el estado para mostrarlo; no se pierde
            log.exception("Fallo en el reindexado")
            with self._lock:
                self._status = replace(
                    self._status, state="error", error=str(exc), finished_at=_now()
                )
            return
        with self._lock:
            self._status = replace(self._status, state="done", report=report, finished_at=_now())
