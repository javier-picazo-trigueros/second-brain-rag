from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import Settings
from secondbrain.domain import Hit
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.store.manifest import Manifest
from tests.fakes import FakeEmbedder, ScriptedStore

Build = Callable[..., tuple[HybridRetriever, ScriptedStore]]


def hit(path: str, score: float, text: str = "texto del chunk", **payload: Any) -> Hit:
    base = {"note_path": path, "heading_path": "Tema", "page": None, "text": text}
    return Hit(score, {**base, **payload})


@pytest.fixture
def build(tmp_path: Path) -> Any:
    manifests: list[Manifest] = []

    def _build(
        hits: list[Hit],
        *,
        chunks: dict[str, int] | None = None,
        concepts: dict[str, list[str]] | None = None,
        copies: list[list[str]] | None = None,
        best: dict[str, Hit] | None = None,
        dense: float | None = 0.6,
        cosines: dict[str, float] | None = None,
        **overrides: Any,
    ) -> tuple[HybridRetriever, ScriptedStore]:
        settings = Settings(_env_file=None, vault_path=tmp_path, **overrides)  # type: ignore[call-arg]
        manifest = Manifest(tmp_path / f"m{len(manifests)}.sqlite")
        manifests.append(manifest)
        counts = dict.fromkeys({h.payload["note_path"] for h in hits}, 3)
        counts.update(dict.fromkeys(concepts or {}, 3))
        counts.update(chunks or {})
        group_of = {p: f"group{i}" for i, g in enumerate(copies or []) for p in g}
        for path in group_of:
            counts.setdefault(path, 3)
        for path, n in counts.items():
            manifest.upsert(path, "h", n)
            manifest.set_meta(path, (concepts or {}).get(path, []), group_of.get(path))
        store = ScriptedStore(hits, best, dense=dense, cosines=cosines)
        return HybridRetriever(settings, FakeEmbedder(), store, manifest), store

    yield _build
    for m in manifests:
        m.close()


def paths(result: Any) -> list[str]:
    return [n.path for n in result.notes]


# --- consulta a Qdrant y agrupado por nota ------------------------------------------


def test_limits_come_from_settings(build: Build) -> None:
    r, store = build([hit("a.md", 0.9)], candidate_limit=77, prefetch_limit=33)
    r.search("consulta")
    assert store.last_search == {"query": "consulta", "limit": 77, "prefetch": 33}


def test_chunks_are_grouped_by_note_and_capped(build: Build) -> None:
    hits = [
        hit("a.md", 0.9, "a1"),
        hit("a.md", 0.8, "a2"),
        hit("a.md", 0.7, "a3"),
        hit("b.md", 0.6),
    ]
    r, _ = build(hits, max_chunks_per_note=2)
    result = r.search("q")
    assert paths(result) == ["a.md", "b.md"]
    assert [c.payload["text"] for c in result.notes[0].chunks] == ["a1", "a2"]
    assert result.notes[0].raw_score == 0.9


def test_notes_rank_by_their_best_chunk_not_by_how_many_chunks_match(build: Build) -> None:
    hits = [hit("a.md", 0.9), hit("b.md", 0.8), hit("b.md", 0.79), hit("b.md", 0.78)]
    r, _ = build(hits)
    assert paths(r.search("q")) == ["a.md", "b.md"]


def test_k_limits_the_number_of_notes(build: Build) -> None:
    r, _ = build([hit(f"n{i}.md", 1 - i / 10) for i in range(6)])
    assert len(r.search("q", k=3).notes) == 3


def test_no_hits_gives_an_empty_result(build: Build) -> None:
    r, store = build([])
    result = r.search("q")
    assert (result.notes, result.related) == ([], [])
    assert not any(call.startswith("r") for call in store.note_calls)  # sin grafo, sin vecinas


def test_note_hit_exposes_title_and_chunk_count(build: Build) -> None:
    r, _ = build([hit("1º/IA/Apuntes.md", 0.9)], chunks={"1º/IA/Apuntes.md": 12})
    (note,) = r.search("q").notes
    assert (note.title, note.n_chunks) == ("Apuntes", 12)


# --- copias exactas --------------------------------------------------------------------------


def test_exact_copies_collapse_into_one_note_preferring_the_unsuffixed_path(build: Build) -> None:
    hits = [hit("x (1).md", 0.9), hit("x.md", 0.85), hit("y.md", 0.5)]
    r, _ = build(hits, copies=[["x (1).md", "x.md"]])
    result = r.search("q")
    assert paths(result) == ["x.md", "y.md"]
    assert result.notes[0].also_in == ("x (1).md",)
    assert result.notes[0].raw_score == 0.9


def test_a_copy_alone_in_the_candidates_is_shown_under_the_canonical_path(build: Build) -> None:
    r, _ = build([hit("x copia.md", 0.9)], copies=[["x copia.md", "x.md"]])
    (note,) = r.search("q").notes
    assert note.path == "x.md"
    assert note.also_in == ("x copia.md",)


def test_also_in_lists_copies_that_were_not_among_the_candidates(build: Build) -> None:
    r, _ = build([hit("x.md", 0.9)], copies=[["x.md", "2º/otra/x.md", "x (2).md"]])
    (note,) = r.search("q").notes
    assert set(note.also_in) == {"2º/otra/x.md", "x (2).md"}


@pytest.mark.parametrize(
    ("group", "expected"),
    [
        (["x (1).md", "x.md", "x - copia.md"], "x.md"),
        (["x (2).md", "x (1).md"], "x (1).md"),  # todas con sufijo: la más corta y luego alfabética
        (["b/doc.md", "a/doc.md"], "a/doc.md"),
        (["carpeta/x.md", "x.md"], "x.md"),
    ],
)
def test_canonical_path_choice(build: Build, group: list[str], expected: str) -> None:
    r, _ = build([hit(group[0], 0.9)], copies=[group])
    assert r.search("q").notes[0].path == expected


# --- libros: penalización por longitud, rebaja y cuota ----------------------------------------


def test_long_notes_are_penalised_by_their_chunk_count(build: Build) -> None:
    hits = [hit("libro.md", 0.60), hit("apunte.md", 0.50)]
    r, _ = build(hits, chunks={"libro.md": 1440, "apunte.md": 8})
    result = r.search("q")
    assert paths(result) == ["apunte.md", "libro.md"]
    assert result.notes[1].raw_score == 0.60
    assert result.notes[1].score < 0.60


def test_notes_up_to_the_reference_size_are_not_penalised(build: Build) -> None:
    r, _ = build([hit("a.md", 0.6)], chunks={"a.md": 8}, length_ref_chunks=8)
    assert r.search("q").notes[0].score == pytest.approx(0.6)


def test_alpha_zero_disables_the_length_penalty(build: Build) -> None:
    hits = [hit("libro.md", 0.60), hit("apunte.md", 0.50)]
    r, _ = build(hits, chunks={"libro.md": 1440}, length_penalty_alpha=0.0)
    assert paths(r.search("q")) == ["libro.md", "apunte.md"]


def test_demote_globs_scale_the_score(build: Build) -> None:
    hits = [hit("manuales/c.md", 0.9), hit("apuntes/c.md", 0.6)]
    r, _ = build(hits, demote_globs=["manuales/*"], demote_factor=0.5)
    result = r.search("q")
    assert paths(result) == ["apuntes/c.md", "manuales/c.md"]
    assert result.notes[1].score == pytest.approx(0.45)


def _quota_hits() -> tuple[list[Hit], dict[str, int]]:
    scores = {"b1": 1.0, "b2": 0.8, "b3": 0.7, "b4": 0.6, "s1": 0.5, "s2": 0.4, "s3": 0.3}
    hits = [hit(f"{n}.md", s) for n, s in scores.items()]
    counts = {f"{n}.md": 300 if n.startswith("b") else 5 for n in scores}
    return hits, counts


def test_quota_limits_big_notes_in_the_top_k(build: Build) -> None:
    hits, counts = _quota_hits()
    r, _ = build(hits, chunks=counts, length_penalty_alpha=0.0, big_note_quota=2)
    assert paths(r.search("q", k=4)) == ["b1.md", "b2.md", "s1.md", "s2.md"]


def test_a_big_note_almost_as_good_as_the_first_ignores_the_quota(build: Build) -> None:
    hits = [hit("b1.md", 1.0), hit("b2.md", 0.97), hit("b3.md", 0.95), hit("b4.md", 0.6)]
    hits.append(hit("s1.md", 0.5))
    counts = {"b1.md": 300, "b2.md": 300, "b3.md": 300, "b4.md": 300, "s1.md": 5}
    r, _ = build(hits, chunks=counts, length_penalty_alpha=0.0, big_note_quota=2)
    assert paths(r.search("q", k=4)) == ["b1.md", "b2.md", "b3.md", "s1.md"]


def test_deferred_big_notes_fill_the_free_slots(build: Build) -> None:
    hits, counts = _quota_hits()
    hits = [h for h in hits if h.payload["note_path"] in {"b1.md", "b2.md", "b3.md", "s1.md"}]
    r, _ = build(hits, chunks=counts, length_penalty_alpha=0.0, big_note_quota=2)
    assert paths(r.search("q", k=4)) == ["b1.md", "b2.md", "b3.md", "s1.md"]


def test_zero_quota_keeps_only_big_notes_near_the_top(build: Build) -> None:
    hits, counts = _quota_hits()
    r, _ = build(hits, chunks=counts, length_penalty_alpha=0.0, big_note_quota=0)
    assert paths(r.search("q", k=3)) == ["b1.md", "s1.md", "s2.md"]


# --- relacionadas por el grafo ------------------------------------------------------------------


def _related_best() -> dict[str, Hit]:
    return {
        "r1.md": hit("r1.md", 0.5, "texto de r1", resumen="Resumen de r1", page=4),
        "r2.md": hit("r2.md", 0.4, "texto de r2", resumen="Resumen de r2"),
    }


def test_related_notes_come_from_shared_concepts_and_are_separate_from_the_ranking(
    build: Build,
) -> None:
    concepts = {"a.md": ["c1"], "r1.md": ["c1"], "r2.md": ["c1"], "otra.md": ["c9"]}
    r, _ = build([hit("a.md", 0.9)], concepts=concepts, best=_related_best())
    result = r.search("q")
    assert paths(result) == ["a.md"]
    assert {n.path for n in result.related} == {"r1.md", "r2.md"}
    first = next(n for n in result.related if n.path == "r1.md")
    assert (first.via, first.seeds) == (("c1",), ("a.md",))
    assert (first.resumen, first.page, first.snippet) == ("Resumen de r1", 4, "texto de r1")


def test_related_excludes_notes_already_in_the_ranking(build: Build) -> None:
    concepts = {"a.md": ["c1"], "b.md": ["c1"], "r1.md": ["c1"]}
    r, _ = build([hit("a.md", 0.9), hit("b.md", 0.8)], concepts=concepts)
    assert [n.path for n in r.search("q").related] == ["r1.md"]


def test_related_excludes_exact_copies_of_the_results(build: Build) -> None:
    concepts = {"a.md": ["c1"], "a (1).md": ["c1"], "r1.md": ["c1"]}
    r, _ = build([hit("a.md", 0.9)], concepts=concepts, copies=[["a.md", "a (1).md"]])
    assert [n.path for n in r.search("q").related] == ["r1.md"]


def test_related_copies_are_collapsed(build: Build) -> None:
    concepts = {"a.md": ["c1"], "r1.md": ["c1"], "r1 (1).md": ["c1"]}
    r, _ = build([hit("a.md", 0.9)], concepts=concepts, copies=[["r1.md", "r1 (1).md"]])
    (rel,) = r.search("q").related
    assert rel.path == "r1.md"


def test_graph_budget_and_switch(build: Build) -> None:
    concepts = {"a.md": ["c1"], **{f"r{i}.md": ["c1"] for i in range(6)}}
    r, store = build([hit("a.md", 0.9)], concepts=concepts, graph_budget=2)
    assert len(r.search("q").related) == 2
    store.note_calls.clear()
    assert r.search("q", with_graph=False).related == []
    assert not any(call.startswith("r") for call in store.note_calls)  # sin grafo, sin vecinas


def test_related_without_a_best_chunk_is_still_listed(build: Build) -> None:
    concepts = {"a.md": ["c1"], "r1.md": ["c1"]}
    r, _ = build([hit("a.md", 0.9)], concepts=concepts)
    (rel,) = r.search("q").related
    assert (rel.path, rel.resumen, rel.snippet) == ("r1.md", None, None)


# --- similitud densa (señal de confianza) -----------------------------------------------------


def test_result_carries_the_best_dense_similarity(build: Build) -> None:
    r, _ = build([hit("a.md", 0.9)], dense=0.73)
    assert r.search("q").top_similarity == 0.73


def test_similarity_is_reported_even_without_hits(build: Build) -> None:
    r, _ = build([], dense=0.21)
    assert r.search("q").top_similarity == 0.21


def test_similarity_is_none_when_the_index_is_empty(build: Build) -> None:
    r, _ = build([], dense=None)
    assert r.search("q").top_similarity is None


# --- corte por coseno de la nota ------------------------------------------------------


def three_notes() -> list[Hit]:
    return [hit("a.md", 0.9), hit("b.md", 0.8), hit("c.md", 0.7)]


def test_notes_far_below_the_best_cosine_are_dropped(build: Build) -> None:
    r, _ = build(three_notes(), cosines={"a.md": 0.70, "b.md": 0.66, "c.md": 0.40})
    assert paths(r.search("q")) == ["a.md", "b.md"]


def test_cosine_margin_is_relative_to_the_best_note(build: Build) -> None:
    # 0,57 supera el mínimo absoluto (0,55) pero queda 0,13 por debajo del mejor (0,70).
    r, _ = build(three_notes()[:2], cosines={"a.md": 0.70, "b.md": 0.57})
    assert paths(r.search("q")) == ["a.md"]


def test_absolute_floor_can_leave_no_evidence(build: Build) -> None:
    r, _ = build(three_notes(), cosines={"a.md": 0.45, "b.md": 0.44, "c.md": 0.30})
    assert r.search("q").notes == []


def test_floor_and_margin_come_from_settings(build: Build) -> None:
    r, _ = build(
        three_notes(),
        cosines={"a.md": 0.70, "b.md": 0.50, "c.md": 0.40},
        min_note_cosine=0.30,
        cosine_margin=0.35,
    )
    assert paths(r.search("q")) == ["a.md", "b.md", "c.md"]


def test_cutoff_happens_before_taking_top_k(build: Build) -> None:
    hits = [hit(f"{n}.md", 0.9 - i / 20) for i, n in enumerate("abcd")]
    r, _ = build(hits, cosines={"a.md": 0.70, "b.md": 0.30, "c.md": 0.68, "d.md": 0.66})
    assert paths(r.search("q", k=2)) == ["a.md", "c.md"]


def test_unknown_cosine_is_looked_up_for_that_note(build: Build) -> None:
    best = {"b.md": hit("b.md", 0.66), "c.md": hit("c.md", 0.30)}
    r, _ = build(three_notes(), cosines={"a.md": 0.70}, best=best)
    assert paths(r.search("q")) == ["a.md", "b.md"]


def test_a_note_with_no_cosine_at_all_is_dropped_when_others_have_one(build: Build) -> None:
    r, _ = build(three_notes(), cosines={"a.md": 0.70})
    assert paths(r.search("q")) == ["a.md"]


def test_cosine_is_exposed_on_the_note(build: Build) -> None:
    r, _ = build(three_notes()[:1], cosines={"a.md": 0.70})
    assert r.search("q").notes[0].cosine == 0.70


def test_only_paths_restricts_the_search(build: Build) -> None:
    r, store = build(three_notes())
    r.search("q", only_paths=["a.md"])
    assert store.last_only_paths == ["a.md"]
