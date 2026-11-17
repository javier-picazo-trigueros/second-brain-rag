"""Esquemas pydantic de la API: lo que entra y lo que sale por HTTP."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- salud ----------------------------------------------------------------------------------


class LoadedModelOut(BaseModel):
    name: str
    vram_mib: float
    expires_at: str | None = None


class OllamaOut(BaseModel):
    ok: bool
    version: str | None = None
    models: dict[str, bool] = Field(default_factory=dict)
    loaded: list[LoadedModelOut] = Field(default_factory=list)
    error: str | None = None


class QdrantOut(BaseModel):
    ok: bool
    points: int | None = None
    error: str | None = None


class VaultOut(BaseModel):
    ok: bool
    path: str


class GpuOut(BaseModel):
    used_mib: int
    total_mib: int


class HealthOut(BaseModel):
    status: str = Field(description="ok | degraded | down")
    ollama: OllamaOut
    qdrant: QdrantOut
    vault: VaultOut
    gpu: GpuOut | None = None
    hints: list[str] = Field(default_factory=list)


class StatsOut(BaseModel):
    notes: int
    chunks: int
    points: int
    duplicate_groups: int
    concepts: int
    last_sync: str | None = None


# --- búsqueda -------------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)
    graph: bool = True
    # Filtros: O dentro de cada lista, Y entre listas.
    asignaturas: list[str] = Field(default_factory=list, max_length=20)
    cursos: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=50)


class ChunkOut(BaseModel):
    heading_path: str
    page: int | None = None
    text: str
    score: float


class NoteHitOut(BaseModel):
    path: str
    title: str
    score: float
    raw_score: float
    n_chunks: int
    asignatura: str | None = None
    curso: str | None = None
    tags: list[str] = Field(default_factory=list)
    also_in: list[str] = Field(default_factory=list)
    chunks: list[ChunkOut]


class RelatedOut(BaseModel):
    path: str
    title: str
    score: float
    via: list[str]
    seeds: list[str]
    resumen: str | None = None
    heading_path: str | None = None
    page: int | None = None
    snippet: str | None = None


class FacetValueOut(BaseModel):
    value: str
    count: int


class FacetsOut(BaseModel):
    asignaturas: list[FacetValueOut] = Field(default_factory=list)
    cursos: list[FacetValueOut] = Field(default_factory=list)
    tags: list[FacetValueOut] = Field(default_factory=list)


class SubjectOut(BaseModel):
    name: str
    notes: int


class SearchResponse(BaseModel):
    notes: list[NoteHitOut]
    related: list[RelatedOut]
    top_similarity: float | None = None
    confidence: str
    facets: FacetsOut = Field(default_factory=FacetsOut)


# --- respuesta ------------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    k: int | None = Field(None, ge=1, le=20)


# --- notas y grafo --------------------------------------------------------------------------


class NeighborOut(BaseModel):
    path: str
    title: str
    score: float
    via: list[str]


class BacklinkOut(BaseModel):
    path: str
    title: str


class NoteOut(BaseModel):
    path: str
    title: str
    asignatura: str | None = None
    curso: str | None = None
    frontmatter: dict[str, Any]
    tags: list[str]
    concepts: list[str]
    links: list[str]
    body: str
    related: list[NeighborOut]
    # Destino de cada [[enlace]] -> notas candidatas (vacío: no existe; varias: ambiguo).
    resolved_links: dict[str, list[str]] = Field(default_factory=dict)
    backlinks: list[BacklinkOut] = Field(default_factory=list)
    obsidian_url: str = ""


class ConceptOut(BaseModel):
    name: str
    notes: int = Field(description="Notas del vault que tratan este concepto")
    idf: float


class NeighborsOut(BaseModel):
    path: str
    concepts: list[ConceptOut]
    neighbors: list[NeighborOut]


# --- reindexado -----------------------------------------------------------------------------


class FailureOut(BaseModel):
    path: str
    error: str


class ReindexReportOut(BaseModel):
    indexed: int
    unchanged: int
    empty: int
    deleted: int
    failed: list[FailureOut]


class ReindexStatusOut(BaseModel):
    state: str = Field(description="idle | running | done | error")
    done: int
    total: int
    current: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    report: ReindexReportOut | None = None
    error: str | None = None


class ErrorOut(BaseModel):
    detail: str


# --- apuntes generados ------------------------------------------------------------------------


class GeneratedPreviewRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=400_000)
    asignatura: str | None = Field(None, max_length=200)
    tema: int | None = Field(None, ge=0, le=999)
    sources: list[str] = Field(default_factory=list, max_length=200)


class GeneratedPreviewOut(BaseModel):
    path: str  # relativa al vault: dónde se guardaría
    content: str  # lo que se escribiría, tal cual


class GeneratedSaveRequest(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=500_000)


class GeneratedSaveOut(BaseModel):
    path: str
    obsidian_url: str
