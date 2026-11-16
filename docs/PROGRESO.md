# Progreso

Se actualiza en cada checkpoint.

## Estado

| Fase | Estado |
|---|---|
| 0. Andamiaje | Terminada y aprobada (rama `feat/fase-0-andamiaje`, merge a `main`) |
| 1. Parser, chunking, indexación incremental | En curso (rama `feat/fase-1-indexacion`) |
| 2. Grafo y watcher | Pendiente |
| 3. Respuesta, API, MCP e interfaz web | Pendiente |
| 4. Evals | Pendiente |

## Fase 0: resultado

- `pyproject.toml` (src layout), `docker-compose.yml` (Qdrant `v1.20.2`, volumen `qdrant_data`),
  `.env.example`, `tasks.ps1` (install, test, lint, typecheck, up, index, dev).
- Venv en `C:\venvs\second-brain`, fuera del repo.
- `tests/fixtures/vault/`: 10 notas, 3 conceptos y 6 señuelos que deben excluirse.
- Verificado: pytest (17 passed), ruff, `mypy --strict`.
- Licencia PolyForm Noncommercial 1.0.0.

## Decisiones aprobadas (Fase 1)

Sobre el diseño de `referencia_fase1.md`:

1. **Enlaces:** se ignora el campo `original` del frontmatter y los enlaces a archivos que no son notas
   (`.pdf`, imágenes).
2. **Páginas:** los encabezados `## Página N` no forman parte de `heading_path`. El número de página se
   guarda como metadato `page` en el chunk y en el payload de Qdrant, para poder citar la página.
3. **Protocolos:** `Indexer` depende de los protocolos `Embedder` y `Store` y se testea con fakes.
4. **Huella de configuración:** el hash del manifest incluye modelo de embeddings, `chunk_max_chars`,
   `chunk_min_chars` y versión del chunker, para reindexar al cambiar cualquiera de ellos.
5. **BM25 offline:** `fastembed` descarga una sola vez `Qdrant/bm25`; su caché se fija en `data/`
   (ignorada por git). Tras la primera ejecución todo funciona sin conexión.

## Siguiente paso

Fase 1 con TDD, en este orden: parser, chunker, manifest, indexer (con fakes), store Qdrant
(integración), CLI (`brain index`, `brain search`, `brain stats`).
