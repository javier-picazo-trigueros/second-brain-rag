from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from secondbrain.store.manifest import Manifest


@dataclass(frozen=True, slots=True)
class Related:
    """Nota vecina de las semillas en el grafo, con el motivo de la relación."""

    path: str
    score: float
    via: tuple[str, ...]  # conceptos que la conectan con las semillas
    seeds: tuple[str, ...]  # semillas desde las que se llegó


class ConceptGraph:
    """Grafo nota -> concepto -> notas. Los conceptos son los nodos intermedios (hubs).

    Una nota se relaciona con otra cuando comparten algún concepto. Un concepto raro (pocas notas)
    aporta más que uno genérico: el peso es idf = ln(N / df).
    """

    def __init__(self, note_concepts: Mapping[str, Sequence[str]]) -> None:
        self._concepts = {path: tuple(cs) for path, cs in note_concepts.items()}
        by_concept: dict[str, list[str]] = defaultdict(list)
        for path in sorted(self._concepts):
            for concept in dict.fromkeys(self._concepts[path]):
                by_concept[concept].append(path)
        self._notes = {c: tuple(paths) for c, paths in by_concept.items()}
        self._n = len(self._concepts)

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> ConceptGraph:
        return cls(manifest.note_concepts())

    def concepts_of(self, path: str) -> tuple[str, ...]:
        return self._concepts.get(path, ())

    def notes_of(self, concept: str) -> tuple[str, ...]:
        return self._notes.get(concept, ())

    def idf(self, concept: str) -> float:
        df = len(self._notes.get(concept, ()))
        return math.log(self._n / df) if df else 0.0

    def expand(
        self,
        seeds: Sequence[tuple[str, float]],
        *,
        fanout_cap: int,
        budget: int,
        min_idf: float = 0.0,
        exclude: Collection[str] = (),
    ) -> list[Related]:
        """Notas vecinas de las semillas, ordenadas por relevancia y recortadas al presupuesto.

        Por cada (semilla, concepto) solo cuentan las `fanout_cap` vecinas que más conceptos
        comparten con la semilla, para que un concepto muy poblado no inunde el resultado.
        """
        seed_paths = {path for path, _ in seeds}
        blocked = seed_paths | set(exclude)
        scores: dict[str, float] = defaultdict(float)
        via: dict[str, dict[str, None]] = defaultdict(dict)
        origin: dict[str, dict[str, None]] = defaultdict(dict)

        for seed, seed_score in seeds:
            seed_concepts = self.concepts_of(seed)
            for concept in seed_concepts:
                weight = self.idf(concept)
                if weight < min_idf:
                    continue
                candidates = [p for p in self.notes_of(concept) if p not in blocked]
                candidates.sort(key=lambda p: (-self._overlap(seed_concepts, p), p))
                for neighbor in candidates[:fanout_cap]:
                    scores[neighbor] += seed_score * weight
                    via[neighbor][concept] = None
                    origin[neighbor][seed] = None

        ranked = sorted(scores, key=lambda p: (-scores[p], p))[: max(budget, 0)]
        return [Related(p, scores[p], tuple(via[p]), tuple(origin[p])) for p in ranked]

    def _overlap(self, seed_concepts: Sequence[str], other: str) -> float:
        shared = set(seed_concepts) & set(self.concepts_of(other))
        return sum(self.idf(c) for c in shared)
