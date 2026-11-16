from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from secondbrain.config import Settings

log = logging.getLogger(__name__)
_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class LoadedModel:
    name: str
    vram_mib: float
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class OllamaStatus:
    ok: bool
    version: str | None = None
    models: dict[str, bool] = field(default_factory=dict)  # modelo necesario -> instalado
    loaded: list[LoadedModel] = field(default_factory=list)  # modelos en memoria ahora
    error: str | None = None


@dataclass(frozen=True, slots=True)
class QdrantStatus:
    ok: bool
    points: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class VaultStatus:
    ok: bool
    path: str


@dataclass(frozen=True, slots=True)
class GpuMemory:
    used_mib: int
    total_mib: int


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: str  # ok | degraded | down
    ollama: OllamaStatus
    qdrant: QdrantStatus
    vault: VaultStatus
    gpu: GpuMemory | None
    hints: list[str]


def gpu_memory() -> GpuMemory | None:
    """VRAM usada y total según nvidia-smi, o None si no hay GPU NVIDIA o no responde."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        used, total = (int(x.strip()) for x in out.stdout.splitlines()[0].split(","))
    except (ValueError, IndexError):
        return None
    return GpuMemory(used, total)


def _installed(installed: set[str], wanted: str) -> bool:
    if ":" in wanted:
        return wanted in installed
    return any(name.split(":")[0] == wanted for name in installed)


class HealthChecker:
    def __init__(
        self, settings: Settings, ollama: httpx.Client, qdrant_points: Callable[[], int]
    ) -> None:
        self._s = settings
        self._ollama = ollama
        self._points = qdrant_points

    def check(self) -> HealthReport:
        hints: list[str] = []
        ollama = self._check_ollama(hints)
        qdrant = self._check_qdrant(hints)
        vault_ok = self._s.vault_path.is_dir()
        if not vault_ok:
            hints.append("El vault no existe: revisa BRAIN_VAULT_PATH en el .env.")
        if not (ollama.ok and qdrant.ok):
            status = "down"
        elif not vault_ok or not all(ollama.models.values()):
            status = "degraded"
        else:
            status = "ok"
        return HealthReport(
            status=status,
            ollama=ollama,
            qdrant=qdrant,
            vault=VaultStatus(vault_ok, str(self._s.vault_path)),
            gpu=gpu_memory(),
            hints=hints,
        )

    def _get(self, path: str) -> dict[str, Any]:
        response = self._ollama.get(path, timeout=5)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def _check_ollama(self, hints: list[str]) -> OllamaStatus:
        try:
            version = str(self._get("/api/version").get("version"))
            installed = {m["name"] for m in self._get("/api/tags").get("models", [])}
            loaded = [
                LoadedModel(m["name"], m.get("size_vram", 0) / _MIB, m.get("expires_at"))
                for m in self._get("/api/ps").get("models", [])
            ]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            hints.append(
                f"Ollama no responde en {self._s.ollama_url}: arráncalo con `ollama serve`."
            )
            return OllamaStatus(ok=False, error=str(exc) or type(exc).__name__)
        models = {m: _installed(installed, m) for m in (self._s.embed_model, self._s.llm_model)}
        for model, present in models.items():
            if not present:
                hints.append(f"Falta el modelo {model}: ejecuta `ollama pull {model}`.")
        return OllamaStatus(ok=True, version=version, models=models, loaded=loaded)

    def _check_qdrant(self, hints: list[str]) -> QdrantStatus:
        try:
            return QdrantStatus(ok=True, points=self._points())
        except Exception as exc:  # sondeo de estado: cualquier fallo significa "no disponible"
            log.info("Qdrant no disponible: %s", exc)
            hints.append(
                f"Qdrant no responde en {self._s.qdrant_url}: arráncalo con `.\\tasks.ps1 up`."
            )
            return QdrantStatus(ok=False, error=str(exc) or type(exc).__name__)
