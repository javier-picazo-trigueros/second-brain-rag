from __future__ import annotations

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
    assert kinds == ["embed", "delete", "upsert"]


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
