from __future__ import annotations

import math

import pytest

from secondbrain.retrieval.graph import ConceptGraph
from tests.env import Env

CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
SEMAFOROS = "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md"
ENLACES = "1º/IA/Enlaces y embeds.md"
IPTABLES = "4º/Seguridad/Cortafuegos con iptables.md"


def _graph(**notes: list[str]) -> ConceptGraph:
    return ConceptGraph(notes)


def _expand(
    g: ConceptGraph, seeds: list[tuple[str, float]], **kw: object
) -> list[tuple[str, float]]:
    params: dict[str, object] = {"fanout_cap": 5, "budget": 10, **kw}
    return [(r.path, r.score) for r in g.expand(seeds, **params)]  # type: ignore[arg-type]


# --- estructura e idf -----------------------------------------------------------------------


def test_concepts_and_notes_are_indexed_both_ways() -> None:
    g = _graph(a=["x", "y"], b=["y"], c=[])
    assert g.concepts_of("a") == ("x", "y")
    assert g.notes_of("y") == ("a", "b")
    assert g.notes_of("desconocido") == ()
    assert g.concepts_of("desconocida") == ()


def test_idf_is_higher_for_rarer_concepts() -> None:
    g = _graph(a=["raro", "comun"], b=["comun"], c=["comun"], d=[])
    assert g.idf("raro") == pytest.approx(math.log(4 / 1))
    assert g.idf("comun") == pytest.approx(math.log(4 / 3))
    assert g.idf("raro") > g.idf("comun")


# --- expansión ------------------------------------------------------------------------------


def test_neighbors_share_a_concept_and_exclude_the_seed() -> None:
    g = _graph(a=["x"], b=["x"], c=["y"])
    assert [p for p, _ in _expand(g, [("a", 1.0)])] == ["b"]


def test_exclude_removes_candidates() -> None:
    g = _graph(a=["x"], b=["x"], c=["x"])
    assert [p for p, _ in _expand(g, [("a", 1.0)], exclude={"b"})] == ["c"]


def test_unknown_seed_or_isolated_note_expands_to_nothing() -> None:
    g = _graph(a=["x"], b=["y"])
    assert _expand(g, [("desconocida", 1.0)]) == []
    assert _expand(g, [("a", 1.0)]) == []


def test_fanout_cap_limits_neighbors_per_concept() -> None:
    notes = {f"n{i:02d}": ["hub"] for i in range(12)}
    got = _expand(ConceptGraph(notes), [("n00", 1.0)], fanout_cap=5)
    assert len(got) == 5


def test_fanout_prefers_neighbors_sharing_more_concepts_with_the_seed() -> None:
    notes = {"seed": ["hub", "x", "y"], "aaa": ["hub"], "bbb": ["hub"], "zzz": ["hub", "x", "y"]}
    for i in range(6):
        notes[f"fill{i}"] = ["hub"]
    got = [p for p, _ in _expand(ConceptGraph(notes), [("seed", 1.0)], fanout_cap=2)]
    assert "zzz" in got


def test_budget_truncates_the_result_ordered_by_score() -> None:
    g = _graph(a=["x", "y"], b=["x", "y"], c=["x"], d=["y"], e=["x"])
    full = _expand(g, [("a", 1.0)], budget=10)
    assert full[0][0] == "b"  # comparte dos conceptos
    assert [p for p, _ in _expand(g, [("a", 1.0)], budget=2)] == [p for p, _ in full[:2]]
    assert _expand(g, [("a", 1.0)], budget=0) == []


def test_scores_scale_with_the_seed_score() -> None:
    g = _graph(a=["x"], b=["x"], c=["y"], d=["y"])
    got = dict(_expand(g, [("a", 2.0), ("c", 1.0)]))
    assert got["b"] == pytest.approx(2 * g.idf("x"))
    assert got["d"] == pytest.approx(1 * g.idf("y"))


def test_a_note_reached_by_several_seeds_accumulates_score() -> None:
    g = _graph(a=["x"], b=["y"], target=["x", "y"], other=["x"])
    got = dict(_expand(g, [("a", 1.0), ("b", 1.0)]))
    assert got["target"] > got["other"]


def test_via_and_seeds_explain_the_relation() -> None:
    g = _graph(a=["x", "y"], b=["x", "y"], c=["z"])
    (rel,) = g.expand([("a", 1.0)], fanout_cap=5, budget=5)
    assert (rel.path, rel.via, rel.seeds) == ("b", ("x", "y"), ("a",))


def test_min_idf_ignores_generic_concepts() -> None:
    g = _graph(a=["comun"], b=["comun"], c=["comun"], d=["comun"], e=["raro"], f=["raro"])
    assert _expand(g, [("a", 1.0)], min_idf=g.idf("raro")) == []
    assert _expand(g, [("e", 1.0)], min_idf=g.idf("raro")) != []


def test_ties_are_broken_by_path_for_reproducibility() -> None:
    g = _graph(a=["x"], c=["x"], b=["x"])
    assert [p for p, _ in _expand(g, [("a", 1.0)])] == ["b", "c"]


# --- con el vault de ejemplo --------------------------------------------------------------------


def test_graph_from_the_synced_fixture_vault(env: Env) -> None:
    env.indexer().sync()
    g = ConceptGraph.from_manifest(env.manifest)
    related = g.expand([(CARRERA, 1.0)], fanout_cap=5, budget=5)
    assert {r.path for r in related} == {SEMAFOROS, ENLACES}
    assert all(r.via == ("semaforo",) for r in related)
    assert [r.path for r in g.expand([(IPTABLES, 1.0)], fanout_cap=5, budget=5)] == [ENLACES]
