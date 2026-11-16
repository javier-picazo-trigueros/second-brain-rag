from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from secondbrain.config import Settings
from secondbrain.ingest.indexer import Indexer

log = logging.getLogger(__name__)

# Clave especial del debouncer: "hubo cambios en carpetas, hay que reconciliar todo el vault".
_RESYNC = "<resync>"
_RETRY_DELAYS = (0.5, 1.0)  # esperas entre los 3 intentos si OneDrive tiene el fichero bloqueado
_DIRECTORY_EVENTS = frozenset({"created", "deleted", "moved"})  # "modified" salta con cada nota


class Debouncer:
    """Agrupa ráfagas de eventos: una ruta se libera cuando lleva `delay` s sin eventos."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def add(self, key: str, now: float) -> None:
        with self._lock:
            self._last[key] = now

    def due(self, now: float) -> list[str]:
        with self._lock:
            ready = sorted(k for k, t in self._last.items() if now - t >= self._delay)
            for key in ready:
                del self._last[key]
        return ready

    @property
    def pending(self) -> set[str]:
        with self._lock:
            return set(self._last)


@dataclass(slots=True)
class WatchReport:
    indexed: int = 0
    unchanged: int = 0
    empty: int = 0
    removed: int = 0
    resynced: bool = False
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.indexed or self.removed or self.empty or self.resynced or self.failed)


class WatcherService:
    """Mantiene el índice al día con los cambios del vault (solo lo lee, nunca lo modifica).

    La decisión se toma al vencer el debounce y según el estado real del disco: si el fichero
    existe se indexa (el hash del manifest evita reindexar lo que no cambió) y si no, se borra.
    Así un renombrado es, de forma natural, un borrado más un alta.
    """

    def __init__(
        self,
        indexer: Indexer,
        settings: Settings,
        debounce: float = 1.5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._indexer = indexer
        self._s = settings
        self._debouncer = Debouncer(debounce)
        self._clock = clock
        self._sleep = sleep

    @property
    def pending(self) -> set[str]:
        return self._debouncer.pending

    # --- entrada de eventos ---------------------------------------------------------------------

    def _relative(self, path: Path) -> str | None:
        try:
            return path.relative_to(self._s.vault_path).as_posix()
        except ValueError:
            try:
                return path.resolve().relative_to(self._s.vault_path).as_posix()
            except (ValueError, OSError):
                return None

    def _is_note(self, rel: str | None) -> bool:
        if rel is None:
            return False
        name = rel.rsplit("/", 1)[-1]
        if name.startswith("~$") or not name.lower().endswith(".md"):
            return False
        return not self._s.is_excluded(rel)

    def handle(
        self, kind: str, src: Path, dest: Path | None = None, *, is_directory: bool = False
    ) -> None:
        now = self._clock()
        if is_directory:
            if kind in _DIRECTORY_EVENTS and self._relative(src) is not None:
                self._debouncer.add(_RESYNC, now)
            return
        for path in (src, dest):
            rel = self._relative(path) if path is not None else None
            if self._is_note(rel):
                assert rel is not None
                self._debouncer.add(rel, now)

    # --- procesado ------------------------------------------------------------------------------

    def process_due(self) -> WatchReport:
        report = WatchReport()
        due = self._debouncer.due(self._clock())
        if _RESYNC in due:
            self._resync(report)
            return report  # la reconciliación completa ya cubre las rutas sueltas vencidas
        for rel in due:
            self._apply(rel, report)
        return report

    def _resync(self, report: WatchReport) -> None:
        sync = self._indexer.sync()
        report.resynced = True
        report.indexed += sync.indexed
        report.unchanged += sync.unchanged
        report.empty += sync.empty
        report.removed += sync.deleted
        report.failed.extend(sync.failed)

    def _apply(self, rel: str, report: WatchReport) -> None:
        abs_path = self._s.vault_path / rel
        if not abs_path.is_file():
            self._remove(rel, report)
            return
        try:
            status = self._index_with_retries(abs_path)
        except FileNotFoundError:  # desapareció entre la comprobación y la lectura
            self._remove(rel, report)
            return
        except OSError as exc:  # sigue bloqueado tras los reintentos (OneDrive sincronizando)
            log.warning("No se pudo leer %s: %s", rel, exc)
            report.failed.append((rel, repr(exc)))
            return
        except Exception as exc:  # un fallo en una nota no debe tumbar el watcher; se reporta
            log.exception("Fallo indexando %s", rel)
            report.failed.append((rel, repr(exc)))
            return
        if status == "indexed":
            report.indexed += 1
            log.info("indexada: %s", rel)
        elif status == "empty":
            report.empty += 1
        else:
            report.unchanged += 1

    def _index_with_retries(self, abs_path: Path) -> str:
        for delay in _RETRY_DELAYS:
            try:
                return self._indexer.index_file(abs_path)
            except PermissionError as exc:
                log.info("%s está en uso (%s); reintento en %.1f s", abs_path.name, exc, delay)
                self._sleep(delay)
        return self._indexer.index_file(abs_path)

    def _remove(self, rel: str, report: WatchReport) -> None:
        if self._indexer.is_indexed(rel):
            self._indexer.remove(rel)
            report.removed += 1
            log.info("eliminada del índice: %s", rel)

    # --- bucle real -----------------------------------------------------------------------------

    def run(self, stop: threading.Event, poll: float = 0.2) -> None:
        observer = Observer()
        observer.schedule(_Forwarder(self), str(self._s.vault_path), recursive=True)
        observer.start()
        try:
            while not stop.wait(poll):
                report = self.process_due()
                if report.changed:
                    log.info(
                        "watch: indexadas=%d vacías=%d eliminadas=%d fallos=%d%s",
                        report.indexed,
                        report.empty,
                        report.removed,
                        len(report.failed),
                        " (resync)" if report.resynced else "",
                    )
        finally:
            observer.stop()
            observer.join()


class _Forwarder(FileSystemEventHandler):
    """Traduce los eventos de watchdog a llamadas a `WatcherService.handle`."""

    def __init__(self, service: WatcherService) -> None:
        self._service = service

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type not in {"created", "modified", "deleted", "moved"}:
            return  # "opened", "closed"...: no cambian el contenido
        src = Path(os.fsdecode(event.src_path))
        raw_dest = getattr(event, "dest_path", "")
        dest = Path(os.fsdecode(raw_dest)) if raw_dest else None
        self._service.handle(event.event_type, src, dest, is_directory=event.is_directory)
