# Referencia de diseño: Fase 1 (aprobada)

Documento de referencia para Claude Code. Contiene la arquitectura validada, el presupuesto de VRAM, la estructura del repositorio y el código de referencia de la Fase 1 (parser, chunking, indexación incremental en Qdrant con embeddings de Ollama).

El código es una base aprobada, no un dogma: si se detecta un error o una mejora clara, se propone antes de desviarse. Implementar siguiendo TDD (los tests se escriben primero).

---

## 1. Presupuesto de VRAM (RTX 4060, 8 GB)

Cifras estimadas: el módulo `evals/` debe medirlas de verdad con `nvidia-smi`.

| Componente | VRAM aprox. |
|---|---|
| Escritorio Windows y navegador | 0,5-1 GB |
| `qwen2.5:7b` Q4_K_M (pesos) | 4,7 GB |
| KV cache con `num_ctx=8192` (28 capas, 4 cabezas KV) | ~0,45 GB |
| Buffers de cómputo | ~0,3-0,5 GB |
| `bge-m3` (F16) | ~1,2 GB |
| **Total** | **~7,2-8 GB, sin holgura** |

`qwen3:8b` no encaja: 36 capas y 8 cabezas KV, la caché a 8k supera 1,2 GB y no cabe junto al embedder.

Decisiones:
1. **Embeddings en CPU en consulta** (`options.num_gpu=0`). Una consulta en CPU tarda ~100-300 ms y libera 1,2 GB. En la ingesta masiva se puede usar GPU (`BRAIN_EMBED_ON_CPU=false`) con el LLM descargado.
2. **LLM:** `qwen2.5:7b` con `num_ctx=8192`. Ollama arrancado con `OLLAMA_FLASH_ATTENTION=1` y `OLLAMA_KV_CACHE_TYPE=q8_0` (reduce la caché a la mitad).
3. **Presupuesto de contexto:** 6 chunks de ~450 tokens (~2,7k) + resúmenes de vecinos del grafo (~1k) + sistema e historial (~1k) ≈ 5k tokens. 8k sobra.

Modelos necesarios (el usuario los descarga):
```
ollama pull qwen2.5:7b
ollama pull bge-m3
```

## 2. Decisiones de arquitectura

- **Qdrant en vez de Chroma.** Qdrant soporta vectores dispersos y fusión RRF en el servidor: un solo motor hace la búsqueda híbrida. BM25 con `fastembed` (`Qdrant/bm25`, idioma `spanish`). Las notas en inglés tendrán peor léxico: se mide en evals.
- **Los conceptos son los hubs del grafo.** El frontmatter tiene `conceptos: ["[[...]]"]`. La expansión va nota → concepto → otras notas, con tope de fan-out por concepto (p. ej. `git-flow` enlaza 21 notas) y ponderada por rareza (idf). Las notas de `_conceptos/` no se indexan como texto: solo son nodos.
- **Pipeline determinista primero, agente encima.** Los modelos 7B hacen tool calling irregular. Primero `retrieve → expand → answer`; el agente después, con 3-4 herramientas tipadas.
- **MCP es la interfaz de más valor:** Claude Code podrá llamar a `search_notes` y `get_note`.
- **Watchdog sobre OneDrive** genera eventos duplicados y temporales: debounce (~1,5 s) y comparación por hash contra el manifest.
- **Evals:** preguntas sintéticas generadas por el LLM a partir de notas aleatorias; Hit@k y MRR para decidir con datos si el grafo y el híbrido aportan.
- **Contexto del vault:** hay README en UTF-16, placeholders `*(sin texto extraíble: ver PDF)*`, notas con `sin_texto: true`, y `.py`/`.txt` de herramientas en la raíz (no son notas). `CLAUDE.md` y `_INDICE.md` se excluyen del índice.

## 3. Estructura del repositorio

```
second-brain-rag/
├─ pyproject.toml
├─ docker-compose.yml
├─ .env.example
├─ README.md
├─ tasks.ps1
├─ src/secondbrain/
│  ├─ config.py            # pydantic-settings
│  ├─ domain.py            # ParsedNote, Chunk, Hit
│  ├─ cli.py               # typer: index | search | stats | watch
│  ├─ ingest/
│  │  ├─ parser.py         # frontmatter, tags, wikilinks
│  │  ├─ chunker.py        # por encabezados, respeta código
│  │  ├─ indexer.py        # sync incremental
│  │  └─ watcher.py        # (fase 2) watchdog + debounce
│  ├─ embeddings/ollama.py
│  ├─ store/
│  │  ├─ qdrant.py         # denso + BM25 + RRF
│  │  └─ manifest.py       # sqlite: ruta -> hash
│  ├─ retrieval/           # (fase 2) hybrid.py, graph.py
│  ├─ agent/               # (fase 3) tools.py, agent.py
│  └─ api/                 # (fase 3) main.py (FastAPI), mcp_server.py
├─ frontend/               # (fase 3) React + Vite + TS + Tailwind
├─ evals/                  # (fase 4) dataset, hit_mrr.py, vram_latency.py
├─ tests/
│  └─ fixtures/vault/
└─ docs/
   ├─ referencia_fase1.md
   └─ architecture.md
```

## 4. Código de referencia

### pyproject.toml
```toml
[project]
name = "secondbrain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27", "pydantic>=2.7", "pydantic-settings>=2.3",
  "qdrant-client>=1.10", "fastembed>=0.4", "pyyaml>=6.0",
  "typer>=0.12", "tenacity>=8.3", "watchdog>=4.0",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5", "mypy>=1.10", "types-PyYAML"]
[project.scripts]
brain = "secondbrain.cli:app"
[tool.setuptools.packages.find]
where = ["src"]
[tool.mypy]
strict = true
ignore_missing_imports = true
[tool.ruff]
line-length = 100
[tool.pytest.ini_options]
markers = ["integration: requiere Ollama y Qdrant en marcha"]
```

### docker-compose.yml
Docker Desktop tiene que estar abierto. Fijar la versión de la imagen cuando funcione.
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["qdrant_data:/qdrant/storage"]
    restart: unless-stopped
volumes:
  qdrant_data:
```

### .env.example
```
BRAIN_VAULT_PATH=C:\ruta\a\tu\vault
BRAIN_EMBED_ON_CPU=false
```

### src/secondbrain/config.py
```python
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRAIN_", env_file=".env", extra="ignore")

    vault_path: Path
    exclude_dirs: frozenset[str] = frozenset({
        ".obsidian", ".git", ".trash", "node_modules", "__MACOSX", ".venv", "venv",
        "_conceptos", "_archivo", "_pruebas",
    })
    exclude_files: frozenset[str] = frozenset({"CLAUDE.md", "_INDICE.md"})

    ollama_url: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    embed_batch_size: int = Field(16, ge=1, le=128)
    embed_on_cpu: bool = False
    embed_keep_alive: str = "30s"

    qdrant_url: str = "http://localhost:6333"
    collection: str = "vault_chunks"
    bm25_language: str = "spanish"

    manifest_path: Path = Path("data/manifest.sqlite")
    chunk_max_chars: int = Field(1800, ge=400)
    chunk_min_chars: int = Field(300, ge=50)

    @field_validator("vault_path")
    @classmethod
    def _vault_exists(cls, v: Path) -> Path:
        if not v.is_dir():
            raise ValueError(f"El vault no existe: {v}")
        return v.resolve()
```

### src/secondbrain/domain.py
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedNote:
    path: str                      # relativa al vault, con "/"
    title: str
    frontmatter: dict[str, Any]
    tags: tuple[str, ...]
    links: tuple[str, ...]         # destinos de [[...]] (cuerpo + frontmatter)
    body: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    note_path: str
    note_title: str
    heading_path: tuple[str, ...]
    text: str
    position: int
    tags: tuple[str, ...]
    links: tuple[str, ...]
    asignatura: str | None
    curso: str | None
    resumen: str | None

    @property
    def embed_text(self) -> str:
        """Texto que se embebe: contexto (título > encabezados) + contenido."""
        ctx = " > ".join((self.note_title, *self.heading_path))
        return f"{ctx}\n\n{self.text}"


@dataclass(frozen=True, slots=True)
class Hit:
    score: float
    payload: dict[str, Any]
```

### src/secondbrain/ingest/parser.py
```python
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from secondbrain.domain import ParsedNote

_FM = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_FENCED = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_WIKILINK = re.compile(r"(?<!!)\[\[([^\]\|#\^\n]+)(?:[#^][^\]\|\n]*)?(?:\|[^\]\n]*)?\]\]")
_TAG = re.compile(r"(?<![\w/&])#([^\W\d][\w/\-]*)")


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):  # hay README en UTF-16 en el vault
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text[m.end():]
    return (data if isinstance(data, dict) else {}), text[m.end():]


def _strip_code(text: str) -> str:
    return _INLINE_CODE.sub("", _FENCED.sub("", text))


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_strings(v)


def _dedupe(items: Iterator[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i for i in items if i))


def parse_note(abs_path: Path, vault: Path) -> ParsedNote:
    raw = abs_path.read_bytes()
    fm, body = _split_frontmatter(_decode(raw))
    scan = _strip_code(body)

    def targets(text: str) -> Iterator[str]:
        for m in _WIKILINK.finditer(text):
            yield m.group(1).strip().rsplit("/", 1)[-1]

    fm_links = (t for s in _iter_strings(fm) for t in targets(s))
    links = _dedupe(iter((*targets(scan), *fm_links)))

    raw_tags = fm.get("tags", [])
    fm_tags = [raw_tags] if isinstance(raw_tags, str) else list(_iter_strings(raw_tags))
    inline = (m.group(1) for m in _TAG.finditer(scan))
    tags = _dedupe(t.lstrip("#").lower() for t in (*fm_tags, *inline))

    return ParsedNote(
        path=abs_path.relative_to(vault).as_posix(),
        title=abs_path.stem,
        frontmatter=fm,
        tags=tags,
        links=links,
        body=body,
        content_hash=hashlib.sha256(raw).hexdigest(),
    )
```

### src/secondbrain/ingest/chunker.py
```python
from __future__ import annotations

import re
import uuid

from secondbrain.domain import Chunk, ParsedNote

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_LINE = re.compile(r"^[ \t]*(```|~~~)")
_PLACEHOLDER = re.compile(r"^\*\(sin texto extraíble[^\n]*\)\*[ \t]*$", re.M)
_MIN_KEEP = 40


def _sections(body: str) -> list[tuple[tuple[str, ...], str]]:
    """Divide por encabezados (ignorando los que están dentro de bloques de código)."""
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    out: list[tuple[tuple[str, ...], str]] = []
    in_fence, marker = False, ""

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            out.append((tuple(t for _, t in stack), text))
        buf.clear()

    for line in body.splitlines():
        fence = _FENCE_LINE.match(line)
        if fence:
            if not in_fence:
                in_fence, marker = True, fence.group(1)
            elif fence.group(1) == marker:
                in_fence = False
        elif not in_fence:
            h = _HEADING.match(line)
            if h:
                flush()
                level = len(h.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, h.group(2).strip()))
                continue
        buf.append(line)
    flush()
    return out


def _blocks(text: str) -> list[str]:
    """Párrafos separados por línea en blanco; un bloque de código es atómico."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence, marker = False, ""
    for line in text.splitlines():
        fence = _FENCE_LINE.match(line)
        if fence:
            if not in_fence:
                in_fence, marker = True, fence.group(1)
            elif fence.group(1) == marker:
                in_fence = False
            cur.append(line)
        elif not in_fence and not line.strip():
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _hard_split(block: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for line in block.splitlines():
        while len(line) > max_chars:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:max_chars])
            line = line[max_chars:]
        if cur and len(cur) + len(line) + 1 > max_chars:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def _pack(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    cur = ""
    for block in _blocks(text):
        for part in [block] if len(block) <= max_chars else _hard_split(block, max_chars):
            if cur and len(cur) + 2 + len(part) > max_chars:
                pieces.append(cur)
                cur = part
            else:
                cur = f"{cur}\n\n{part}" if cur else part
    if cur:
        pieces.append(cur)
    return pieces


def chunk_note(note: ParsedNote, max_chars: int = 1800, min_chars: int = 300) -> list[Chunk]:
    body = _PLACEHOLDER.sub("", note.body)
    pieces: list[tuple[tuple[str, ...], str]] = []
    for heading_path, text in _sections(body):
        for piece in _pack(text, max_chars):
            if pieces and len(piece) < min_chars:
                prev_path, prev_text = pieces[-1]
                label = f"**{heading_path[-1]}**\n" if heading_path and heading_path != prev_path else ""
                if len(prev_text) + len(label) + len(piece) + 2 <= max_chars:
                    pieces[-1] = (prev_path, f"{prev_text}\n\n{label}{piece}")
                    continue
            pieces.append((heading_path, piece))

    fm = note.frontmatter
    meta = {k: (str(fm[k]) if fm.get(k) is not None else None)
            for k in ("asignatura", "curso", "resumen")}
    return [
        Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note.path}#{i}")),
            note_path=note.path,
            note_title=note.title,
            heading_path=hp,
            text=text,
            position=i,
            tags=note.tags,
            links=note.links,
            **meta,
        )
        for i, (hp, text) in enumerate(p for p in pieces if len(p[1]) >= _MIN_KEEP)
    ]
```

### src/secondbrain/embeddings/ollama.py
```python
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from secondbrain.config import Settings


class OllamaEmbedder:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.Client(base_url=settings.ollama_url, timeout=120.0)
        self._model = settings.embed_model
        self._batch = settings.embed_batch_size
        self._keep_alive = settings.embed_keep_alive
        self._cpu = settings.embed_on_cpu

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
           retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    def _embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self._model, "input": texts, "keep_alive": self._keep_alive,
        }
        if self._cpu:
            payload["options"] = {"num_gpu": 0}
        r = self._client.post("/api/embed", json=payload)
        r.raise_for_status()
        embeddings: list[list[float]] = r.json()["embeddings"]
        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            out.extend(self._embed(texts[i : i + self._batch]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def dimension(self) -> int:
        return len(self.embed_query("dimension probe"))
```

### src/secondbrain/store/manifest.py
```python
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class Manifest:
    """Ruta -> hash del contenido indexado. Permite sincronizar de forma incremental."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS notes ("
                "path TEXT PRIMARY KEY, hash TEXT NOT NULL, n_chunks INTEGER NOT NULL)"
            )
            self._db.commit()

    def get(self, path: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT hash FROM notes WHERE path=?", (path,)).fetchone()
        return None if row is None else str(row[0])

    def upsert(self, path: str, content_hash: str, n_chunks: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO notes(path, hash, n_chunks) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, n_chunks=excluded.n_chunks",
                (path, content_hash, n_chunks),
            )
            self._db.commit()

    def delete(self, path: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM notes WHERE path=?", (path,))
            self._db.commit()

    def paths(self) -> set[str]:
        with self._lock:
            return {str(r[0]) for r in self._db.execute("SELECT path FROM notes")}

    def totals(self) -> tuple[int, int]:
        with self._lock:
            n, c = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(n_chunks),0) FROM notes"
            ).fetchone()
        return int(n), int(c)
```

### src/secondbrain/store/qdrant.py
```python
from __future__ import annotations

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from secondbrain.config import Settings
from secondbrain.domain import Chunk, Hit

DENSE = "dense"
SPARSE = "bm25"
_UPSERT_BATCH = 64


class VectorStore:
    def __init__(self, settings: Settings, dim: int) -> None:
        self._client = QdrantClient(url=settings.qdrant_url)
        self._sparse = SparseTextEmbedding(model_name="Qdrant/bm25", language=settings.bm25_language)
        self._name = settings.collection
        self._dim = dim

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self._name):
            vectors = self._client.get_collection(self._name).config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) else None
            if size != self._dim:
                raise RuntimeError(
                    f"La colección usa dim={size} pero el embedder da {self._dim}. "
                    "Cambiaste de modelo: borra la colección y el manifest y reindexa."
                )
            return
        self._client.create_collection(
            self._name,
            vectors_config={DENSE: models.VectorParams(size=self._dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field in ("note_path", "tags", "asignatura", "curso"):
            self._client.create_payload_index(
                self._name, field_name=field, field_schema=models.PayloadSchemaType.KEYWORD
            )

    @staticmethod
    def _payload(c: Chunk) -> dict[str, object]:
        return {
            "note_path": c.note_path, "note_title": c.note_title,
            "heading_path": " > ".join(c.heading_path), "position": c.position,
            "text": c.text, "tags": list(c.tags), "links": list(c.links),
            "asignatura": c.asignatura, "curso": c.curso, "resumen": c.resumen,
        }

    def upsert_chunks(self, chunks: list[Chunk], dense: list[list[float]]) -> None:
        sparse = list(self._sparse.embed([c.embed_text for c in chunks]))
        points = [
            models.PointStruct(
                id=c.id,
                vector={
                    DENSE: d,
                    SPARSE: models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
                },
                payload=self._payload(c),
            )
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        for i in range(0, len(points), _UPSERT_BATCH):
            self._client.upsert(self._name, points=points[i : i + _UPSERT_BATCH], wait=True)

    def delete_note(self, note_path: str) -> None:
        self._client.delete(
            self._name,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="note_path", match=models.MatchValue(value=note_path))
            ])),
        )

    def search(self, query: str, query_dense: list[float], limit: int = 8,
               prefetch: int = 40) -> list[Hit]:
        s = next(iter(self._sparse.query_embed(query)))
        res = self._client.query_points(
            self._name,
            prefetch=[
                models.Prefetch(query=query_dense, using=DENSE, limit=prefetch),
                models.Prefetch(
                    query=models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist()),
                    using=SPARSE, limit=prefetch,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [Hit(score=p.score, payload=dict(p.payload or {})) for p in res.points]

    def count(self) -> int:
        return self._client.count(self._name, exact=True).count
```

### src/secondbrain/ingest/indexer.py
```python
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.chunker import chunk_note
from secondbrain.ingest.parser import parse_note
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

log = logging.getLogger(__name__)
Status = Literal["indexed", "unchanged", "empty"]


@dataclass(slots=True)
class SyncReport:
    indexed: int = 0
    unchanged: int = 0
    empty: int = 0
    deleted: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


class Indexer:
    def __init__(self, settings: Settings, embedder: OllamaEmbedder,
                 store: VectorStore, manifest: Manifest) -> None:
        self._s = settings
        self._embedder = embedder
        self._store = store
        self._manifest = manifest

    def iter_note_paths(self) -> Iterator[Path]:
        for root, dirs, files in os.walk(self._s.vault_path):
            dirs[:] = [d for d in dirs if d not in self._s.exclude_dirs]  # poda: no entra en node_modules
            for f in files:
                if f.lower().endswith(".md") and f not in self._s.exclude_files:
                    yield Path(root) / f

    def index_file(self, abs_path: Path) -> Status:
        note = parse_note(abs_path, self._s.vault_path)
        if self._manifest.get(note.path) == note.content_hash:
            return "unchanged"
        chunks = [] if note.frontmatter.get("sin_texto") is True else chunk_note(
            note, self._s.chunk_max_chars, self._s.chunk_min_chars
        )
        vectors = self._embedder.embed_documents([c.embed_text for c in chunks]) if chunks else []
        self._store.delete_note(note.path)       # se embebe antes de borrar: ventana mínima sin datos
        if chunks:
            self._store.upsert_chunks(chunks, vectors)
        self._manifest.upsert(note.path, note.content_hash, len(chunks))
        return "indexed" if chunks else "empty"

    def remove(self, rel_path: str) -> None:
        self._store.delete_note(rel_path)
        self._manifest.delete(rel_path)

    def sync(self) -> SyncReport:
        report = SyncReport()
        seen: set[str] = set()
        for abs_path in self.iter_note_paths():
            rel = abs_path.relative_to(self._s.vault_path).as_posix()
            seen.add(rel)
            try:
                status = self.index_file(abs_path)
            except Exception as exc:  # una nota rota no debe parar el sync
                log.exception("Fallo indexando %s", rel)
                report.failed.append((rel, repr(exc)))
                continue
            if status == "indexed":
                report.indexed += 1
                log.info("indexada: %s", rel)
            elif status == "empty":
                report.empty += 1
            else:
                report.unchanged += 1
        for gone in self._manifest.paths() - seen:
            self.remove(gone)
            report.deleted += 1
        return report
```

Nota para la implementación: `Indexer` debería depender de protocolos (`Embedder`, `Store`) en vez de las clases concretas, para poder testearlo con fakes sin Ollama ni Qdrant.

### src/secondbrain/cli.py
```python
from __future__ import annotations

import logging

import typer

from secondbrain.config import Settings
from secondbrain.embeddings.ollama import OllamaEmbedder
from secondbrain.ingest.indexer import Indexer
from secondbrain.store.manifest import Manifest
from secondbrain.store.qdrant import VectorStore

app = typer.Typer(no_args_is_help=True, help="Segundo cerebro local (RAG sobre Obsidian)")


def _build() -> tuple[Settings, OllamaEmbedder, VectorStore, Manifest]:
    settings = Settings()  # type: ignore[call-arg]
    embedder = OllamaEmbedder(settings)
    store = VectorStore(settings, dim=embedder.dimension())
    store.ensure_collection()
    return settings, embedder, store, Manifest(settings.manifest_path)


@app.command()
def index() -> None:
    """Sincroniza el vault con el índice (solo notas nuevas, cambiadas o borradas)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings, embedder, store, manifest = _build()
    r = Indexer(settings, embedder, store, manifest).sync()
    typer.echo(f"indexadas={r.indexed} sin_cambios={r.unchanged} vacias={r.empty} "
               f"borradas={r.deleted} fallos={len(r.failed)}")
    for path, err in r.failed:
        typer.echo(f"  FALLO {path}: {err}", err=True)


@app.command()
def search(query: str, k: int = 5) -> None:
    """Búsqueda híbrida (vectorial + BM25, fusión RRF)."""
    _, embedder, store, _ = _build()
    for h in store.search(query, embedder.embed_query(query), limit=k):
        p = h.payload
        snippet = str(p["text"]).replace("\n", " ")[:160]
        typer.echo(f"{h.score:.3f}  {p['note_path']}  [{p['heading_path']}]\n       {snippet}")


@app.command()
def stats() -> None:
    _, _, store, manifest = _build()
    notes, chunks = manifest.totals()
    typer.echo(f"notas={notes} chunks_manifest={chunks} puntos_qdrant={store.count()}")


if __name__ == "__main__":
    app()
```

### tests/test_chunker.py (ejemplo)
```python
from secondbrain.domain import ParsedNote
from secondbrain.ingest.chunker import chunk_note


def _note(body: str) -> ParsedNote:
    return ParsedNote("a/n.md", "n", {}, (), (), body, "h")


def test_heading_path_and_code_fence_is_atomic() -> None:
    body = "# A\n\ntexto largo " + "x" * 80 + "\n\n## B\n\n```python\n# no es encabezado\nprint(1)\n```\n"
    chunks = chunk_note(_note(body), max_chars=400, min_chars=10)
    assert any(c.heading_path == ("A", "B") and "print(1)" in c.text for c in chunks)
    assert not any(c.heading_path[-1] == "no es encabezado" for c in chunks)
```

## 5. Criterios de aceptación de la Fase 1

- `brain index` funciona dos veces seguidas y la segunda reporta `indexadas=0` (el incremental funciona).
- Al editar una nota y relanzar, solo se reindexa esa.
- Búsquedas por término exacto (`iptables`, `nullifier`) y por significado devuelven la nota correcta.
- Tests, ruff y mypy --strict en verde.

## 6. Fases siguientes (resumen)

- **Fase 2:** `watcher.py` (watchdog con debounce) y `retrieval/graph.py` (expansión nota → concepto → notas con tope de fan-out e idf).
- **Fase 3:** pipeline de respuesta con citas `[[nota]]`, FastAPI, servidor MCP e interfaz web.
- **Fase 4:** `evals/` con dataset sintético, Hit@k, MRR, latencia y VRAM medida.
