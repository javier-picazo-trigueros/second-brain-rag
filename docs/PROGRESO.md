# Progreso

Se actualiza en cada checkpoint.

## Estado

| Fase | Estado |
|---|---|
| 0. Andamiaje | Terminada, aprobada y publicada (`main`) |
| 1. Parser, chunking, indexación incremental | Terminada, aprobada y publicada (`main`) |
| 2. Grafo, búsqueda híbrida y watcher | Plan pendiente de aprobación |
| 3. Respuesta, API, MCP e interfaz web | Pendiente |
| 4. Evals | Pendiente |

## Fase 0: resultado

- `pyproject.toml` (src layout), `docker-compose.yml` (Qdrant `v1.20.2`, volumen `qdrant_data`),
  `.env.example`, `tasks.ps1` (install, test, lint, typecheck, up, index, dev).
- Venv en `C:\venvs\second-brain`, fuera del repo.
- `tests/fixtures/vault/`: 10 notas, 3 conceptos y 6 señuelos que deben excluirse.
- Licencia PolyForm Noncommercial 1.0.0.

## Fase 1: resultado

Módulos (TDD, test en rojo antes de cada uno): `ingest/parser.py`, `ingest/chunker.py`,
`store/manifest.py`, `config.py`, `ingest/indexer.py`, `embeddings/ollama.py`, `store/qdrant.py`,
`cli.py` (`brain index`, `brain search`, `brain stats`), `net.py`, `protocols.py`.

Verificación:

- 145 tests en verde (incluidos 15 de integración con Ollama y Qdrant reales sobre el vault de ejemplo).
- Cobertura total 99 %; `ingest/` 98-100 %.
- `ruff check`, `ruff format --check` y `mypy --strict` sin errores.

Indexación del vault real (1.000 notas, solo lectura):

| Ejecución | Resultado | Tiempo |
|---|---|---|
| 1.ª `brain index` (embedder en GPU) | indexadas=951 vacías=47 fallos=2 | 25 min 24 s |
| 2.ª (reintenta las 2 fallidas) | indexadas=2 sin_cambios=998 fallos=0 | 1 min 5 s |
| 3.ª | indexadas=0 sin_cambios=1000 fallos=0 | 8,8 s |

`brain stats`: `notas=1000 chunks_manifest=23236 puntos_qdrant=23236`. Coincide con el ensayo en
seco de parseo y chunking (23.236 chunks, 0 fallos de parseo, 36 notas con `sin_texto`).
Chunk medio de ~1.100 caracteres; una nota (un libro) llega a 1.440 chunks. Ritmo de ingesta en GPU:
~15 chunks/s.

Búsquedas de ejemplo (embedder en CPU, ~2,7 s por invocación de la CLI incluyendo arranque; la
primera tardó 6,5 s por la carga del modelo):

- `iptables` (término exacto): los 5 resultados son de la misma nota de Seguridad (4º).
- `cómo evitar condiciones de carrera entre hilos` (semántica): notas de CAR, Sistemas y EDA sobre
  carreras de datos y concurrencia.
- `how does TCP congestion control work` (inglés): los 5 resultados son de la sección de control de
  congestión de los apuntes de Redes (3º).

### Incidencias

1. **Antivirus que inspecciona HTTPS.** Avast Web Shield firma el tráfico TLS con su propia CA, que
   Windows confía pero `certifi` no. Rompió pip (el 24.0 del venv) y la descarga del modelo BM25. Se
   usa `truststore` (almacén de certificados del SO) solo antes de esa descarga; no se desactiva
   ninguna verificación.
2. **`localhost` lento hacia Qdrant.** Resuelve antes a IPv6 (`::1`) y Docker publica solo IPv4:
   ~2 s por conexión nueva. El valor por defecto es `127.0.0.1:6333` (la suite pasó de 216 s a 24 s).
3. **2 notas fallaron con `400 Bad Request` de Ollama en la primera pasada.**
   - Una nota de AOC (7 chunks): el log de Ollama muestra un crash del runner CUDA (`illegal memory
     access`, `llama-server terminated`) justo antes del 400.
   - El libro de Sistemas Operativos (1.319 chunks): 400 tras 20 s **sin ningún error registrado en Ollama**; causa no
     determinada.
   - No se reproducen: ningún chunk falla solo ni en lotes de 16, y la 2.ª pasada las indexó bien.
     Hipótesis (no verificada): inestabilidad transitoria con la GPU casi llena (7,7 de 8 GB durante
     la ingesta). El indexer las aisló como estaba previsto y no tocó su manifest.

   - Decisión aprobada: `embed_batch_size` por defecto baja de 16 a 8 (más margen de VRAM) y los 400
     **no** se reintentan, para no enmascarar errores reales. No altera la huella de configuración,
     así que no fuerza a reindexar.

### Distribución de chunks por nota

953 notas con chunks (47 vacías), 23.236 chunks; mediana 8 chunks por nota, p90 39, p99 283.

| # | Chunks | % | % acum. | Nota |
|--:|--:|--:|--:|---|
| 1 | 1440 | 6,2 | 6,2 | Cálculo (2º): libro, tomo I |
| 2 | 1319 | 5,7 | 11,9 | Sistemas Operativos (2º): libro de referencia |
| 3 | 1255 | 5,4 | 17,3 | PGPI (4º): guía de gestión de proyectos |
| 4 | 856 | 3,7 | 21,0 | AOC (2º): libro de arquitectura de computadores |
| 5 | 614 | 2,6 | 23,6 | PGPI (4º): documento largo de la asignatura |
| 6 | 602 | 2,6 | 26,2 | Sistemas Operativos (2º): apuntes de C |
| 7 | 569 | 2,4 | 28,6 | Ética (3º): libro de historia de la ética |
| 8 | 331 | 1,4 | 30,1 | IA II (3º): tesis |
| 9 | 328 | 1,4 | 31,5 | Sistemas Operativos (2º): apuntes de Bash |
| 10 | 283 | 1,2 | 32,7 | IA I (3º): artículo técnico |
| 11 | 235 | 1,0 | 33,7 | IA II (3º): libro de interacción persona-ordenador |
| 12 | 187 | 0,8 | 34,5 | Proyecto de hackathon (4º): documento de diseño |
| 13 | 179 | 0,8 | 35,3 | Cálculo (2º): libro, tomo II |
| 14 | 179 | 0,8 | 36,1 | Cálculo (2º): copia del tomo II |
| 15 | 150 | 0,6 | 36,7 | IA II (3º): apuntes de una unidad |

Concentración: top-5 = 23,6 %, top-10 = 32,7 %, top-25 = 42,3 %, top-50 = 52,9 %. Notas con más de
100 chunks: 37 (3,9 % de las notas) que suman el 47,9 % del total; con más de 500: 7 notas, 28,6 %.

### Observaciones sobre la calidad de búsqueda

- Sin deduplicado por nota: `iptables` devuelve 5 chunks de la misma nota. Se aborda en la Fase 2
  (`retrieval/hybrid.py`).
- Los scores son de fusión RRF y no son comparables entre consultas.
- No hay verdad de referencia todavía: juzgar si la búsqueda semántica es buena o no es tarea de la
  Fase 4 (evals).

## Decisiones aprobadas (Fase 1)

Sobre el diseño de `referencia_fase1.md`:

1. **Enlaces:** se ignora el campo `original` del frontmatter y los enlaces a archivos que no son notas
   (`.pdf`, imágenes).
2. **Páginas:** los encabezados `## Página N` no forman parte de `heading_path`. El número de página se
   guarda como metadato `page` en el chunk y en el payload de Qdrant, para poder citar la página.
3. **Protocolos:** `Indexer` depende de los protocolos `Embedder` y `Store` y se testea con fakes.
4. **Huella de configuración:** el hash del manifest incluye modelo de embeddings, `chunk_max_chars`,
   `chunk_min_chars` y versión del chunker, para reindexar al cambiar cualquiera de ellos. Añadido
   además `bm25_language`, que también cambia los vectores dispersos.
5. **BM25 offline:** `fastembed` descarga una sola vez `Qdrant/bm25`; su caché se fija en
   `data/fastembed_cache` (ignorada por git). Verificado con `HF_HUB_OFFLINE=1`.

## Siguiente paso

Fase 2: `retrieval/graph.py` (expansión nota → concepto → notas con tope de fan-out e idf),
`retrieval/hybrid.py` (denso + BM25 + RRF + grafo + deduplicado por nota, con control para que los
libros largos no dominen) y `ingest/watcher.py`. El plan se presenta antes de programar y espera
aprobación.
