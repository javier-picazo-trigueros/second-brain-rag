# Progreso

Se actualiza en cada checkpoint.

## Estado

| Fase | Estado |
|---|---|
| 0. Andamiaje | Terminada, aprobada y publicada (`main`) |
| 1. Parser, chunking, indexación incremental | Terminada, aprobada y publicada (`main`) |
| 2. Grafo, búsqueda híbrida y watcher | Terminada, aprobada y publicada (`main`) |
| 3a. Respuesta, API y MCP (sin interfaz) | Terminada, aprobada y publicada (`main`) |
| 3b. Interfaz web | En curso (rama `feat/fase-3b-interfaz`): marco, Preguntar y Estado hechos |
| Corrección de calidad | En curso (rama `fix/calidad-respuestas`): recuperación, citas, prompt, latencia y bugs de la interfaz; pendiente de aprobación |
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

## Fase 2: resultado

Módulos (TDD): `retrieval/graph.py`, `retrieval/hybrid.py`, `ingest/watcher.py`, `ingest/text.py`;
ampliaciones de `parser` (conceptos y huella del cuerpo), `manifest` (tablas `note_concepts` y
`body_hash`, con migración de la base de la Fase 1), `config` (parámetros y patrones) y `cli`
(`brain search` híbrido, `brain graph`, `brain watch`, `brain stats` ampliado; tarea `watch`).

Verificación: 280 tests en verde (incluidos los de integración con Ollama y Qdrant reales y uno con
`watchdog` real), cobertura total 99 % (`ingest/` 97-100 %, `retrieval/` 99-100 %), `ruff` y
`mypy --strict` sin errores. Un test (`is_indexed`) se escribió junto con su implementación y no se
observó en rojo.

### Comprobaciones técnicas previas

- **`query_points_groups` con prefetch + RRF (qdrant-client 1.20.0, servidor 1.20.2):** funciona sin
  error pero **no es fiable**: con los mismos datos y la misma consulta ordena distinto que la fusión
  plana (una nota casi última en la fusión plana salía primera agrupada) y sus scores no son los de RRF.
  Decisión: el agrupado por nota se hace **en cliente** sobre una consulta plana con límite amplio
  (`candidate_limit=150`, `prefetch_limit=120`).
- **Copias exactas** (hash del cuerpo normalizado: sin frontmatter, sin placeholders ni marcadores de
  página, NFC, espacios colapsados; mínimo 200 caracteres): **128 grupos** (115 de 2, 12 de 3, 1 de 4),
  142 notas redundantes y 2.222 chunks (9,6 % del total). En 108 grupos las copias están en carpetas o
  asignaturas distintas (un mismo documento reutilizado). 122 grupos tienen una ruta sin sufijo
  `(n)`/`copia`. Además hay 15 grupos de casi-duplicados con contenido distinto, que no se tocan.
- **Error corregido durante la verificación:** la primera versión daba 136 grupos porque las notas
  `sin_texto` (solo `## Página N` y trozos sueltos) con el mismo número de páginas coincidían. Ahora las
  notas `sin_texto` no tienen huella y los marcadores de página no cuentan; el resultado real es 128.

### Búsqueda híbrida (valores por defecto en `Settings`, a ajustar en la Fase 4)

Una consulta plana a Qdrant (denso + BM25 con RRF) y después, en cliente: agrupado por nota (máximo 2
chunks por nota, la nota puntúa por su mejor chunk), colapso de copias exactas (se muestra la ruta sin
sufijo y `también en:` con las demás ubicaciones), rebaja por patrones, penalización por longitud
`1 + α·log2(n/n_ref)` (α=0,1, n_ref=8), cuota de notas grandes (≥200 chunks; máximo 2 salvo que
alcancen el 90 % de la primera) y, aparte del ranking, notas relacionadas por el grafo.

Antes/después con el índice real (embedder en CPU):

| Consulta | Antes (fase 1, 5 chunks) | Después (5 notas) |
|---|---|---|
| término exacto (`iptables`) | 1 nota (5 chunks de la misma) | 5 notas distintas; la mejor conserva el primer puesto |
| semántica (carreras entre hilos) | 5 notas | las mismas 5; una nota larga (118 chunks) baja al último puesto |
| inglés (control de congestión TCP) | 1 nota (5 chunks de la misma) | 5 notas; las 4 últimas con score muy bajo (0,12-0,06 frente a 0,56) |

Observación abierta: en la consulta en inglés la cola de resultados es débil y entran 2 notas grandes
(libro de referencia y artículo) con scores bajos. Candidato para la Fase 4: un umbral relativo
mínimo de score respecto al primero.

### Grafo

915 conceptos, mediana de 2 notas por concepto, máximo 21. Con tope de 5 vecinas por concepto y
presupuesto de 4, una nota con 20 vecinas posibles muestra 4. Hallazgo: el idf **no separa** los
conceptos ambiguos: el más genérico (21 notas) tiene idf 3,86 y uno ambiguo como `redes` (9 notas) 4,71,
frente a 6,21 de un concepto raro; por eso `graph_min_idf` no sirve para filtrarlos. En la búsqueda
de `iptables`, las relacionadas incluyen una nota de otra asignatura conectada solo por `reglas` y dos
por `redes`. Candidato para la Fase 4: exigir 2 conceptos compartidos o rebajar las aristas de un solo
concepto ambiguo.

### Watcher (copia temporal, colección y manifest de prueba aparte, ya eliminados)

Arranque sincroniza las 7 notas copiadas; editar una nota: 1 indexada; crear: 1 indexada; reescribir
con el mismo contenido (como hace OneDrive): sin actividad (el hash del manifest evita reindexar);
ráfaga de 5 guardados seguidos: 1 indexación (debounce de 1,5 s); temporales `~$x.md` y `x.tmp`:
ignorados; renombrar: 1 eliminada y 1 indexada; borrar: 1 eliminada. El párrafo añadido en vivo se
encontró en una búsqueda. El índice real no se tocó (23.236 puntos antes y después).

### Índice real tras la migración

`brain index`: `indexadas=0 sin_cambios=1000` en ~20 s (rellena conceptos y huellas sin embeber nada).
`brain stats`: `notas=1000 chunks_manifest=23236 puntos_qdrant=23236 grupos_de_copias=128 conceptos=915`.

## Fase 3a: resultado

Módulos (TDD): `answer/llm.py` (chat de Ollama en streaming), `answer/context.py` (contexto con
presupuesto de tokens), `answer/prompt.py`, `answer/citations.py` (validación de citas, también en
streaming), `answer/pipeline.py`, `api/` (FastAPI: `app`, `schemas`, `health`, `reindex`, `main`),
`mcp_server.py`, `notes.py`; `brain serve`; rutas ancladas a la raíz del proyecto.

Verificación: 607 tests en verde (incluidos los de integración con Ollama y Qdrant reales: la API
completa con el modelo real y el servidor MCP como proceso stdio lanzado desde otro directorio),
cobertura total 98 %, `ruff` y `mypy --strict` sin errores. Las pruebas de mutación sobre el validador de
citas detectaron un hueco (el límite de longitud de una cita cerrada) que se cubrió con un test.

### Dependencias y entorno

- `fastapi==0.163.1`, `uvicorn==0.54.0` y `mcp==2.3.0` fijadas en `pyproject.toml`. `mcp` 2.x cambió
  su API respecto a 1.x (`MCPServer` en lugar de `FastMCP`, hints en `snake_case`, `ToolError` para
  errores con mensaje visible).
- `pip` no podía leer `pypi.org/simple/mcp/` con el escudo web del antivirus activo (respuesta HTTP
  corrupta, reproducible y solo para ese paquete); se instaló con el escudo desactivado
  temporalmente y se reactivó después. El resto de PyPI funcionaba.
- `.env` y `data/` se resuelven desde la raíz del proyecto, no desde el directorio de trabajo
  (el MCP lo lanza el cliente desde otro sitio). Esto destapó que un test leía el `.env` real:
  toda la suite está ahora aislada de él.

### Presupuesto de tokens y rendimiento (medido con el índice real)

- Tokens por caracteres: 3,29-3,85 medidos con Ollama sobre chunks reales; se estima con 3,0.
  Sobre 4 prompts reales el estimador sobreestimó entre +9 % y +21 % y nunca se quedó corto.
- Prompts reales de 3.600-4.050 tokens con 4.500 de tope de contexto; el test fija que prompt más
  respuesta (1.024) nunca supera 8.192 ni en el peor caso.
- Latencia (arranque en frío / en caliente): recuperación 2,0 s / 0,15-0,25 s (la primera consulta
  carga el embedder en CPU); primer token 7,1 s / 1,8-2,1 s; total 8,8 s / 2,0-5,7 s; carga del modelo
  3,2-6,4 s; generación 45-50 tok/s.
- VRAM (`nvidia-smi` muestreado cada 0,4 s durante cada respuesta): 0 MiB base, **pico 4.915 MiB** con
  `qwen2.5:7b` (4.791 MiB según Ollama) y `num_ctx=8192`; `bge-m3` en CPU ocupa 0 MiB. Quedan ~3.270 MiB
  libres de los 8.188.

### Calibración de la confianza (coseno denso del mejor chunk)

Con consultas **verificadas contra el índice** (cada tema comprobado por escaneo de los 23.236 chunks):

| Grupo | n | mín. | mediana | máx. |
|---|--:|--:|--:|--:|
| Presentes en el vault | 14 | 0,605 | 0,684 | 0,778 |
| Ausentes, mismo ámbito técnico | 8 | 0,443 | 0,550 | 0,604 |
| Ausentes, otro ámbito | 5 | 0,441 | 0,462 | 0,513 |
| Mencionados de pasada (1-8 chunks) | 5 | 0,477 | 0,511 | 0,567 |

No hay umbral que separe perfectamente (0,604 frente a 0,605). Con 0,60 se aceptan el 100 % de los
presentes y 1 de 13 ausentes; es el valor por defecto (`BRAIN_CONFIDENCE_THRESHOLD`). Es un aviso
(`confianza_baja`), nunca un bloqueo.

### Preguntas reales (respuesta, citas y avisos)

Cuatro preguntas contra el índice real a través de `/ask`, tres rondas (tras cada ronda se corrigió lo
observado). Resultado de la última, que es la que refleja el código actual:

1. **Dentro del vault** (política por defecto de iptables): la afirmación principal (`DROP`) cita la
   página correcta y está respaldada. La segunda frase (conexiones establecidas y relacionadas) cita una
   nota cuyo chunk contiene `RELATED` pero **no** `ESTABLISHED`: respaldo parcial con cita formalmente
   válida.
2. **Cruza asignaturas** (carreras de datos en Sistemas Operativos y en OpenMP): el modelo respondió «No lo
   encuentro en el vault» y sugirió dos notas. En rondas anteriores dio una respuesta parcial con notas
   mal asignadas a la asignatura. La recuperación trajo evidencia sobre todo de una asignatura y la teoría
   de la otra solo como pista. Es el caso más débil.
3. **Trampa** (tema ausente: *borrow checker* de Rust): «No lo encuentro en el vault.», con
   `confianza_baja` (0,566).
4. **Extra, mencionado de pasada** (Kubernetes): «No lo encuentro en el vault.», con `confianza_baja`. El modelo
   citó una página inexistente de una nota sin páginas y el validador la marcó `(p. 7 no verificada)`.

Con una sola ejecución por pregunta y un modelo no determinista, estas respuestas **no demuestran
fiabilidad**: la medición seria es la Fase 4 (evals).

### Problemas encontrados y corregidos durante el checkpoint

- **Mi comprobación de «tema ausente» era errónea.** Afirmé que Kubernetes tenía 0 notas en el vault
  basándome en un `grep` que no estaba leyendo los ficheros; el escaneo del índice dio 7 notas. Las
  calibraciones y la pregunta trampa se rehicieron con comprobaciones contra el índice.
- El modelo copiaba la cabecera del contexto detrás de sus citas (`[[Nota]] (EDA, 3º) | encabezado | p. 21`):
  la página dejaba de ir pegada y no se verificaba. Se separó el título citable de los metadatos
  (en una línea etiquetada) y el validador acepta ahora paréntesis intermedios, rangos y listas.
- El modelo repetía literalmente la frase del prompt para sugerir notas; se sustituyó por una plantilla
  fija («Podrías mirar: [[Título]]»). Se añadió «No extrapoles».

### Límites conocidos de la 3a

- **Una cita válida no implica una afirmación respaldada.** Se verifica que la nota y la página existen en
  el contexto, no que lo afirmado salga de ahí. Mitigación posible (3b/4): exigir una cita literal
  corta y comprobar que aparece en el chunk citado.
- **Recuperación en preguntas que cruzan asignaturas**: falta diversificar por asignatura/curso.
- **`contexto_recortado`** aparece casi siempre: el último chunk de evidencia se trunca para caber.
- **MCP:** lo que devuelve sale de la máquina hacia el cliente (documentado en el README).

## Corrección de calidad de las respuestas (rama `fix/calidad-respuestas`)

Motivo: probando la interfaz con el vault real salieron fuentes irrelevantes, respuestas de una frase,
citas que se rompían con títulos con corchetes, visión general inservible y bugs de la interfaz.
Se midió antes de tocar nada (solo lectura sobre el índice) y después de cada cambio con el conjunto de
preguntas de referencia (`brain golden`; 21 preguntas: 8 concretas, 4 de visión general de asignatura,
4 de «tema N», 2 cruzadas y 3 trampas). El fichero con nombres reales es local e ignorado por git.

### Diagnóstico (causas medidas)

- El score RRF solo ordena: una nota con coseno 0,47 quedó primera con 1,00. El coseno denso del mejor
  chunk de cada nota sí separa lo relevante (≥ 0,62) de lo que no (≤ 0,49).
- `asignatura` del frontmatter es la subcarpeta inmediata (`images`, `Parte1`, `TEMA 2`...) o falta (190
  de 953 notas). La carpeta de segundo nivel (`curso/ASIGNATURA/...`) es siempre correcta.
- Los títulos con corchetes rompían `[[Título]]`; el modelo inventaba rangos de página.
- «Contexto recortado» salía casi siempre: avisaba de notas de relleno.
- Latencia: recuperación en caliente 100-220 ms; el embedder de consulta se descargaba a los 30 s
  (recarga de 1,85 s). La generación iba a 9-14 tok/s porque la GPU estaba compartida con otro
  proceso al 100 %; con la GPU libre vuelve a ~50 tok/s.

### Qué cambia

| Área | Cambio |
|---|---|
| Relevancia | Una nota es evidencia solo si el coseno de su mejor chunk llega a 0,55 y no queda más de 0,12 por debajo del mejor (`BRAIN_MIN_NOTE_COSINE`, `BRAIN_COSINE_MARGIN`). Sin evidencia, «No lo encuentro» sin llamar al modelo. |
| Asignaturas | Carpeta de asignatura como asignatura canónica; mapa de alias opcional en `data/aliases.toml` (ejemplo en `docs/aliases.example.toml`). |
| Visión general | «De qué trata X» y «qué se da en el tema N»: se resumen las notas de la asignatura o tema (resumen, conceptos y apartados), sin copias exactas, repartidas por tema. |
| Preguntas cruzadas | Si nombran dos asignaturas, se busca en cada una y se intercalan los resultados. |
| Citas | Identificadores `[S1]`, `[S2]`... por fragmento. El título y la página los pone el sistema; la interfaz funde chips consecutivos de una misma nota («Nota · p. 6, 7»). |
| Prompt | Respuestas completas y estructuradas (~300 palabras), permiso para relacionar fuentes, recordatorio de citar al final del mensaje, plantilla para visión general. |
| Latencia | `embed_keep_alive` 30 min y precalentamiento de la búsqueda al arrancar la API. |
| Interfaz | La conversación vive sobre las rutas (no se pierde al ir a Estado) con historial de la sesión; tarjetas de fuentes con título, asignatura y página separados; sin texto de ayuda dentro de la respuesta; asignatura mostrada = carpeta. |

### Resultados (conjunto de preguntas de referencia)

Recuperación (qué notas ve el modelo; recall/precisión frente a las esperadas):

| Tipo | n | Recall | Precisión | Ruido (notas) | Top-1 |
|---|---|---|---|---|---|
| concrete | 8 | 0,85 → 0,85 | 0,71 → 0,81 | 1,38 → 0,88 | 0,88 → 0,88 |
| overview_subject | 4 | 0,26 → 1,00 | 0,61 → 0,98 | 1,75 → 0,50 | 0,00 → 0,00 |
| overview_topic | 4 | 0,58 → 1,00 | 0,25 → 1,00 | 3,50 → 0,00 | 0,25 → 0,75 |
| cross | 2 | 0,50 → 0,75 | 0,62 → 1,00 | 1,50 → 0,00 | 1,00 → 1,00 |
| trap | 3 | 1,00 → 1,00 | 0,00 → 0,00 | 5,00 → 0,33 | 0,00 → 0,00 |
| TOTAL | 21 | 0,68 → 0,92 | 0,50 → 0,78 | 2,38 → 0,48 | 0,48 → 0,57 |

Respuestas (medias; «antes» con la GPU compartida, «después» con la GPU libre):

| | Antes | Después |
|---|---|---|
| Longitud (caracteres) | 440 | 1.052 |
| Tokens de salida | 129 | 318 |
| Citas válidas / no verificadas | 22 / 3 | 119 / 0 |
| Recuperación | 151 ms | 148 ms |
| Primer token | 9,5 s | 1,3 s |
| Total | 26 s | 7,3 s |
| Trampas respondidas «No lo encuentro» | 3/3 | 3/3 |

La mejora de latencia total se debe sobre todo a haber liberado la GPU, no al código: no es atribuible a
los cambios. El top-1 de las visiones generales es 0 por construcción (no hay un «primero»).

### Límites conocidos

- Una cita válida sigue sin garantizar que la nota respalde la frase (comprobación de respaldo por frase:
  Fase 4).
- Copias casi idénticas con nombres distintos (`Nota`, `Nota (1)`) no se funden si su contenido difiere.
- `3º/SISTEMAS` mezcla sistemas operativos con integración y cloud: el mapa de alias las une por pedido
  del usuario; una visión general de «sistemas operativos» incluye también esos temas.
- Los umbrales (0,55 / 0,12) están calibrados con 21 preguntas; hay que revisarlos si cambia el vault.

## Decisiones aprobadas (Fase 3a)

1. **Citas inválidas:** se marcan en el texto como `[cita no verificada: X]`.
2. **Raíz del proyecto:** `.env` y `data/` se resuelven desde ahí, con test desde otro directorio.
3. **Dependencias:** `fastapi`, `uvicorn` y `mcp` con versiones fijadas; instalación normal de pip con el
   escudo web del antivirus desactivado temporalmente.
4. **`/ask` sin estado** en la 3a; el historial y la reescritura de la pregunta van en la 3b.
5. **Privacidad del MCP:** aceptada y documentada en el README.
6. **Diversificación por asignatura** (preguntas que cruzan asignaturas): a la Fase 4 como **prioridad 1**,
   evaluada con preguntas que crucen asignaturas.
7. **Citas literales:** descartadas. En la Fase 4, comprobación posterior de respaldo (similitud entre cada
   frase y el chunk que cita) que marque las frases con respaldo bajo.
8. **Aparcado para la Fase 4** (además de lo ya anotado): umbral relativo de score, dos conceptos
   compartidos en el grafo y ajuste de α, cuota y umbral de nota grande.

## Decisiones aprobadas (Fase 2)

1. **Libros:** capas 1-3 activas por defecto (un hueco por nota con prefetch ampliado, penalización
   por longitud, cuota de notas grandes), sin exclusión por defecto. Capa 4 disponible con
   `BRAIN_EXCLUDE_GLOBS` y `BRAIN_DEMOTE_GLOBS` (+ `BRAIN_DEMOTE_FACTOR`), sin rutas por defecto: se
   configuran en el `.env` local y se documentan con un ejemplo genérico en `.env.example`.
2. **Copias exactas:** se colapsan al buscar, sin dejar de indexarlas ni tocar el vault. Se muestra una
   sola ruta, preferiblemente sin sufijo `(n)`/`copia`, y las demás ubicaciones en `también en:`.
3. **Relacionadas por grafo:** sección aparte del ranking.
4. **Parámetros:** la penalización (α, n_ref), el umbral de nota grande, la cuota y su excepción, los
   límites del grafo y los de candidatos están en `Settings` para ajustarlos con datos en la Fase 4.
5. **Historial:** el commit de la Fase 0 que nombra el archivo `CLAUDE.md` se deja como está.
6. **Aparcado para la Fase 4:** umbral relativo mínimo de score respecto al primero (cola débil),
   exigir 2 conceptos compartidos o rebajar las aristas de un solo concepto ambiguo, y afinar α, la cuota
   y el umbral de nota grande con Hit@k y MRR.

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

Fase 3b (interfaz web): se presentan los esquemas de cada pantalla (Preguntar, Buscar, Nota, Estado), los
tokens de diseño y cómo se muestran los avisos (confianza baja, citas no verificadas, «no lo encuentro en
el vault»), y se espera el visto bueno antes de programar. Después, Fase 4 (evals), con la diversificación
por asignatura como prioridad 1 y la comprobación de respaldo por frase.
