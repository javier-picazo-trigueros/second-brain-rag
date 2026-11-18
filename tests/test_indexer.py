from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from secondbrain.ingest.indexer import Indexer
from tests.env import Env

CONTENT_NOTES = {
    "1º/IA/Apuntes con paginas vacias.md",
    "1º/IA/Enlaces y embeds.md",
    "1º/IA/Sin frontmatter.md",
    "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md",
    "1º/SISTEMAS OPERATIVOS/Semáforos y monitores.md",
    "2º/DIS/Guia de scripts.md",
    "2º/DIS/README.md",
    "3º/REDES/Network layers.md",
    "3º/SISTEMAS/Temario cloud.md",
    "4º/Seguridad/Cortafuegos con iptables.md",
}
SIN_TEXTO = "3º/SISTEMAS/Temario cloud.md"
CARRERA = "1º/SISTEMAS OPERATIVOS/Condiciones de carrera.md"
IPTABLES = "4º/Seguridad/Cortafuegos con iptables.md"


# --- recorrido del vault ---------------------------------------------------------------------


def test_iter_note_paths_only_yields_real_notes(env: Env) -> None:
    found = {p.relative_to(env.vault).as_posix() for p in env.indexer().iter_note_paths()}
    assert found == CONTENT_NOTES


def test_iter_note_paths_is_sorted_for_reproducibility(env: Env) -> None:
    paths = list(env.indexer().iter_note_paths())
    assert paths == sorted(paths)


# --- primer sync -----------------------------------------------------------------------------


def test_first_sync_indexes_every_note_with_text(env: Env) -> None:
    report = env.indexer().sync()
    assert (report.indexed, report.unchanged, report.empty, report.deleted) == (9, 0, 1, 0)
    assert report.failed == []
    assert env.store.notes == CONTENT_NOTES - {SIN_TEXTO}


def test_manifest_matches_store_after_sync(env: Env) -> None:
    env.indexer().sync()
    assert env.manifest.paths() == CONTENT_NOTES
    assert env.manifest.totals() == (10, env.store.count())


def test_sin_texto_note_produces_no_chunks_and_is_not_embedded(env: Env) -> None:
    env.indexer().sync()
    assert SIN_TEXTO not in env.store.notes
    assert not any("Temario cloud" in t for t in env.embedder.embedded)


def test_sin_texto_flag_wins_even_if_the_body_has_text(env: Env) -> None:
    env.write("1º/IA/Falsa.md", "---\nsin_texto: true\n---\n\n# T\n\n" + "texto real " * 60)
    env.indexer().sync()
    assert "1º/IA/Falsa.md" not in env.store.notes


# --- idempotencia ----------------------------------------------------------------------------


def test_second_sync_indexes_nothing(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    embedded_before = len(env.embedder.embedded)
    report = idx.sync()
    assert (report.indexed, report.unchanged, report.empty, report.deleted) == (0, 10, 0, 0)
    assert len(env.embedder.embedded) == embedded_before


# --- cambios ---------------------------------------------------------------------------------


def test_only_the_changed_note_is_reindexed(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    env.embedder.embedded.clear()
    env.write(CARRERA, "# Condiciones de carrera\n\n" + "contenido nuevo del tema " * 20)
    report = idx.sync()
    assert (report.indexed, report.unchanged) == (1, 9)
    assert env.embedder.embedded
    assert all(t.startswith("Condiciones de carrera") for t in env.embedder.embedded)


def test_reindexing_replaces_stale_chunks(env: Env) -> None:
    idx = env.indexer(chunk_max_chars=500, chunk_min_chars=100)
    idx.sync()
    assert len(env.store.chunks[CARRERA]) > 1
    env.write(CARRERA, "# Condiciones de carrera\n\n" + "contenido nuevo del tema " * 10)
    idx.sync()
    chunks = env.store.chunks[CARRERA]
    assert len(chunks) == 1
    assert "contenido nuevo" in chunks[0].text


def test_note_that_becomes_sin_texto_loses_its_chunks(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    assert CARRERA in env.store.notes
    env.write(CARRERA, "---\nsin_texto: true\n---\n\n*(sin texto extraíble: ver PDF)*\n")
    report = idx.sync()
    assert report.empty == 1
    assert CARRERA not in env.store.notes
    assert env.manifest.totals()[1] == env.store.count()


def test_deleted_note_is_removed_from_store_and_manifest(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    (env.vault / CARRERA).unlink()
    report = idx.sync()
    assert report.deleted == 1
    assert CARRERA not in env.store.notes
    assert CARRERA not in env.manifest.paths()


def test_renamed_note_is_a_delete_plus_an_add(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    new = "1º/SISTEMAS OPERATIVOS/Carreras.md"
    (env.vault / CARRERA).rename(env.vault / new)
    report = idx.sync()
    assert (report.deleted, report.indexed) == (1, 1)
    assert new in env.store.notes and CARRERA not in env.store.notes


def test_changed_config_fingerprint_reindexes_everything(env: Env) -> None:
    env.indexer().sync()
    report = env.indexer(chunk_max_chars=1000).sync()
    assert (report.indexed, report.unchanged) == (9, 0)


def test_same_config_fingerprint_keeps_everything(env: Env) -> None:
    env.indexer().sync()
    report = env.indexer().sync()
    assert report.indexed == 0


# --- robustez --------------------------------------------------------------------------------


def test_embedding_happens_before_the_old_chunks_are_deleted(env: Env) -> None:
    idx = env.indexer()
    idx.index_file(env.vault / CARRERA)
    env.events.clear()
    env.write(CARRERA, "# Condiciones de carrera\n\n" + "contenido nuevo del tema " * 20)
    idx.index_file(env.vault / CARRERA)
    kinds = [kind for kind, _ in env.events]
    assert kinds == ["embed", "upsert", "retire"]


def test_failure_in_one_note_does_not_stop_the_sync(env: Env) -> None:
    env.embedder.fail_on = "iptables"
    report = env.indexer().sync()
    assert [path for path, _ in report.failed] == [IPTABLES]
    assert "fallo simulado" in report.failed[0][1]
    assert report.indexed == 8
    assert IPTABLES not in env.manifest.paths()


def test_failed_note_is_retried_on_the_next_sync(env: Env) -> None:
    idx = env.indexer()
    env.embedder.fail_on = "iptables"
    idx.sync()
    env.embedder.fail_on = None
    report = idx.sync()
    assert (report.indexed, report.failed) == (1, [])
    assert IPTABLES in env.store.notes


def test_failed_reindex_keeps_the_previous_chunks(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    before = list(env.store.chunks[IPTABLES])
    env.write(IPTABLES, "# iptables\n\n" + "texto nuevo sobre iptables " * 30)
    env.embedder.fail_on = "iptables"
    report = idx.sync()
    assert len(report.failed) == 1
    assert env.store.chunks[IPTABLES] == before


def test_remove_deletes_from_store_and_manifest(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    idx.remove(CARRERA)
    assert CARRERA not in env.store.notes
    assert CARRERA not in env.manifest.paths()


def test_index_file_reports_status(env: Env) -> None:
    idx = env.indexer()
    assert idx.index_file(env.vault / CARRERA) == "indexed"
    assert idx.index_file(env.vault / CARRERA) == "unchanged"
    assert idx.index_file(env.vault / SIN_TEXTO) == "empty"


# --- conceptos y copias en el manifest ---------------------------------------------------------


def test_sync_records_the_concepts_of_every_note(env: Env) -> None:
    env.indexer().sync()
    concepts = env.manifest.note_concepts()
    assert concepts[CARRERA] == ("condicion de carrera", "semaforo")
    assert concepts[SIN_TEXTO] == ()
    assert set(concepts) == CONTENT_NOTES


def test_unchanged_notes_get_their_meta_backfilled_without_reindexing(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    env.manifest.set_meta(CARRERA, [], None)  # estado de una base creada antes de la fase 2
    env.embedder.embedded.clear()
    report = idx.sync()
    assert report.indexed == 0
    assert env.embedder.embedded == []
    assert env.manifest.note_concepts()[CARRERA] == ("condicion de carrera", "semaforo")


def test_exact_copies_form_a_duplicate_group(env: Env) -> None:
    original = (env.vault / "1º/IA/Sin frontmatter.md").read_text(encoding="utf-8")
    env.write("1º/IA/Sin frontmatter (1).md", original)
    env.write("2º/DIS/Otra asignatura.md", "---\nasignatura: DIS\n---\n\n" + original)
    env.indexer().sync()
    assert env.manifest.duplicate_groups() == [
        ("1º/IA/Sin frontmatter (1).md", "1º/IA/Sin frontmatter.md", "2º/DIS/Otra asignatura.md")
    ]


def test_notes_without_text_are_not_reported_as_copies(env: Env) -> None:
    env.write(
        "3º/SISTEMAS/Otro temario.md",
        "---\nsin_texto: true\n---\n\n*(sin texto extraíble: ver PDF)*\n",
    )
    env.indexer().sync()
    assert env.manifest.duplicate_groups() == []


def test_concepts_of_a_removed_note_disappear(env: Env) -> None:
    idx = env.indexer()
    idx.sync()
    (env.vault / CARRERA).unlink()
    idx.sync()
    assert CARRERA not in env.manifest.note_concepts()


# --- exclusión por patrones ----------------------------------------------------------------------


def test_excluded_globs_are_not_indexed(env: Env) -> None:
    report = env.indexer(exclude_globs=["3º/*"]).sync()
    assert env.store.notes.isdisjoint({"3º/REDES/Network layers.md", SIN_TEXTO})
    assert (report.indexed, report.empty) == (8, 0)  # 3º aporta 1 nota con texto y 1 sin texto
    assert "3º/REDES/Network layers.md" not in env.manifest.paths()


def test_adding_an_exclusion_removes_the_notes_on_the_next_sync(env: Env) -> None:
    env.indexer().sync()
    assert "3º/REDES/Network layers.md" in env.store.notes
    report = env.indexer(exclude_globs=["3º/REDES/*"]).sync()
    assert report.deleted == 1
    assert "3º/REDES/Network layers.md" not in env.store.notes


def test_removing_an_exclusion_indexes_the_notes_again(env: Env) -> None:
    env.indexer(exclude_globs=["3º/REDES/*"]).sync()
    report = env.indexer().sync()
    assert report.indexed == 1
    assert "3º/REDES/Network layers.md" in env.store.notes


def test_is_indexed_reflects_the_manifest(env: Env) -> None:
    idx = env.indexer()
    assert not idx.is_indexed(CARRERA)
    idx.sync()
    assert idx.is_indexed(CARRERA)
    idx.remove(CARRERA)
    assert not idx.is_indexed(CARRERA)


# --- progreso y última sincronización ------------------------------------


def test_sync_reports_progress_for_every_note(env: Env) -> None:
    seen: list[tuple[int, int, str]] = []
    env.indexer().sync(on_progress=lambda done, total, path: seen.append((done, total, path)))
    assert [d for d, _, _ in seen] == list(range(1, len(CONTENT_NOTES) + 1))
    assert {t for _, t, _ in seen} == {len(CONTENT_NOTES)}
    assert {p for _, _, p in seen} == CONTENT_NOTES


def test_sync_records_the_time_of_the_last_sync(env: Env) -> None:
    from datetime import UTC, datetime

    moment = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
    idx = Indexer(env.settings(), env.embedder, env.store, env.manifest, now=lambda: moment)
    idx.sync()
    assert env.manifest.get_value("last_sync") == "2026-11-16T12:30:00+00:00"


def test_the_last_sync_time_is_not_set_by_other_operations(env: Env) -> None:
    env.indexer().index_file(env.vault / CARRERA)
    assert env.manifest.get_value("last_sync") is None


def test_empty_walk_preserves_populated_index(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = env.indexer()
    idx.sync()
    monkeypatch.setattr(idx, "iter_note_paths", lambda: iter(()))
    report = idx.sync()
    assert report.failed and report.deleted == 0
    assert env.manifest.paths() == CONTENT_NOTES


def test_walk_reports_an_inaccessible_subfolder(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    from typing import Any

    idx = env.indexer()
    idx.sync()
    scandir = os.scandir

    def deny_folder(path: str) -> Any:
        if Path(path).name == "IA":
            raise PermissionError("no se puede leer IA")
        return scandir(path)

    monkeypatch.setattr(os, "scandir", deny_folder)
    report = idx.sync()
    assert report.deleted == 0 and "IA" in report.failed[0][1]
    assert env.manifest.paths() == CONTENT_NOTES


def test_interrupted_walk_preserves_index(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = env.indexer()
    idx.sync()

    def interrupted() -> Iterator[Path]:
        yield env.vault / CARRERA
        raise PermissionError("carpeta inaccesible")

    monkeypatch.setattr(idx, "iter_note_paths", interrupted)
    report = idx.sync()
    assert report.failed and report.deleted == 0
    assert env.manifest.paths() == CONTENT_NOTES
