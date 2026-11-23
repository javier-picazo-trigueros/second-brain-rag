# Progreso

Se actualiza en cada checkpoint.

## Checkpoint actual · Entrega 1 de fiabilidad

18 de noviembre de 2026. Rama local `feat/entrega-1-fiabilidad`, basada en
`feat/fase-3c-apuntes-ejercicios`. Entrega verificada y pendiente de autorización para integrar y publicar.

| Caso reproducido sobre fixtures | Antes | Resultado verificado |
|---|---|---|
| Recorrido vacío con diez notas indexadas | Las diez se trataban como borradas | Cero borradas, diez conservadas y fallo informado |
| Fallo de BM25 o de un lote de upsert | La versión anterior desaparecía o se veía solo parte de la nueva | El lector recupera todos los fragmentos antiguos y el reintento publica los nuevos |
| Consulta durante la publicación | Agrupar por nota admitía varios fragmentos sin distinguir versión | Selección de generación en ambas ramas de la búsqueda; el lector en curso termina antes de retirar sus puntos |
| Fallo al retirar puntos antiguos | La retirada precedía a la publicación | La nueva versión ya está disponible; el siguiente recorrido reintenta la limpieza |
| Cambio de etiquetas o enlaces con igual ruta | El catálogo conservaba los datos anteriores | Una revisión persistente invalida etiquetas, enlaces inversos y grupos en caché del catálogo |
| Cita válida para otra parte de los apuntes | Se aceptaba y la relevancia se etiquetaba como alta | Se marca en esa parte y se comunica relevancia desconocida |

La preparación de vectores y la subida por lotes usan identificadores distintos para cada generación.
La publicación confirma en SQLite la generación, el hash y los metadatos de la nota en una transacción.
Las lecturas de Qdrant conservan la transacción lectora durante la consulta o la paginación. El manifiesto
usa el diario de reversión de SQLite para que el commit espere a los lectores anteriores.
La primera sincronización tras actualizar reindexará el contenido para recoger los enlaces con carpeta.
Las pruebas usaron fixtures, manifiestos temporales y colecciones de prueba.

El proxy de Vite cubre las rutas de asignaturas y notas generadas. El renderizador comprueba el origen
de las imágenes y la página restringe las imágenes al mismo origen. Las preguntas admiten 4.000 caracteres
tanto en la API como en el prompt. Las llamadas directas que superan ese límite reciben un aviso al
terminar. Los enlaces cualificados conservan la carpeta, incluso si se escribió una ruta abreviada del vault.

**Comprobaciones ejecutadas**

- Pytest completo con integración local y cobertura: 973 pruebas aprobadas, 1 omitida por permisos de
  symlinks en Windows. Cobertura conjunta de `ingest/` y `retrieval/`: 99 %. El cliente Qdrant en memoria
  avisa de que omite los índices de payload. La prueba de publicación también pasó contra Qdrant real.
- Vitest: 417 pruebas aprobadas en 30 archivos. Edge, con la compilación de producción y una nota sintética:
  2 marcadores visibles, 0 elementos con recurso remoto y 0 peticiones externas.
- Ruff y formato: 97 archivos conformes. Mypy estricto: 98 archivos sin errores. TypeScript y ESLint:
  código de salida 0. Compilación de producción correcta, con el aviso de tamaño del bundle principal de Vite.

**Siguiente checkpoint.** Esperar aprobación para merge y push. La entrega 2 guardará el progreso
por partes en `data/` y medirá la generación larga con el modelo de referencia.

## Siguiente paso

Antes de integrar esta rama hay trabajo previo, resumido y priorizado en
[`docs/revision-2026-11-19.md`](revision-2026-11-19.md): la revisión de solo lectura de esta entrega
encontró un bloqueo de la búsqueda durante la publicación de notas (alta), el borrado omitido ante fallos
por nota y la falta de índice de payload para `generation` (medias), y confirmó el inventario de privacidad.
Ese documento incluye también la valoración de los informes de modelos, el orden propuesto para las
Entregas 2-4 y la lista completa de pendientes (Fase 4 y fase 3c). Este paso queda a la espera de tu
decisión sobre los puntos 1-7 de esa lista.

## Estado histórico por fases

| Fase | Estado |
|---|---|
| 0. Andamiaje | Terminada, aprobada y publicada (`main`) |
| 1. Parser, chunking, indexación incremental | Terminada, aprobada y publicada (`main`) |
| 2. Grafo, búsqueda híbrida y watcher | Terminada, aprobada y publicada (`main`) |
| 3a. Respuesta, API y MCP (sin interfaz) | Terminada, aprobada y publicada (`main`) |
| 3b. Interfaz web, checkpoint 1 | Terminada, aprobada y publicada (`main`): marco, Preguntar con el diseño aprobado, Estado, API que sirve `dist` |
| 3b. Interfaz web, checkpoint 2 | Plan (Buscar, Nota, enlaces, «Abrir en Obsidian», KaTeX) pendiente de aprobación |
| Corrección de calidad | Terminada, aprobada y publicada (`main`): recuperación, citas `[S#]`, visión general, prompt, latencia y bugs de la interfaz |
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

### Segunda ronda: preguntas escritas «como se habla»

Al probar con frases reales («de q va la asignatura de…», «cuantos temas tiene…», con faltas), 2 de 3
salían mal. Causas medidas: el detector exigía una frase exacta («de q» y «artificicial» no
encajaban), así que iban por búsqueda normal; una nota de otra asignatura salía como si fuera de ésta;
el número de temas no existía como dato; y la plantilla de visión general se aplicaba también a un
tema suelto, donde el modelo inventaba «un total de 6 temas».

| Cambio | Resultado |
|---|---|
| Intención por señales sueltas (abreviaturas, sin tildes, relleno); un alias tolera una falta solo en palabras largas y nunca en números | Las 3 frases literales y 11 variantes se reconocen; 6 preguntas concretas siguen siendo búsquedas |
| IA I / IA II sin ambigüedad; las notas `DM - Unit` de la carpeta de IA II pasan a Data Mining (un `include` mueve la nota) | IA I 13 notas, IA II 40, Data Mining 46 |
| El número de temas sale del índice (`Unit N` / `Tema N`) y entra al prompt como dato | IA II 7, IA I 7, Data Mining 8 (0 a 7), Sistemas Operativos 8 |
| La visión general excluye libros (≥ `BRAIN_BIG_NOTE_CHUNKS`) y guías docentes, y con temario numerado solo lista el temario | Desaparecen el libro y la guía de otra asignatura |
| Plantilla propia para asignatura (frase inicial, nº de temas, 2-3 frases por tema, «Destacaría») y para un tema | Sin aviso de «confianza baja» en visión general |
| «Un par de párrafos» (u otro número) pasa al modelo como instrucción explícita | Se respeta |

Golden set ampliado a 28 preguntas (7 informales). Recuperación, antes → después:

| Tipo | n | Recall | Precisión | Ruido (notas) |
|---|---|---|---|---|
| concretas | 8 | 0,85 → 0,85 | 0,81 → 0,81 | 0,88 → 0,88 |
| visión general de asignatura | 9 | 0,57 → 0,97 | 0,66 → 0,99 | 0,78 → 0,11 |
| «tema N» | 6 | 0,89 → 1,00 | 0,89 → 1,00 | 0,33 → 0,00 |
| cruzadas | 2 | 0,75 → 0,75 | 1,00 → 1,00 | 0,00 → 0,00 |
| trampas | 3 | 1,00 → 1,00 | — | 0,33 → 0,33 |
| **Total** | **28** | **0,78 → 0,93** | **0,71 → 0,84** | **0,61 → 0,32** |

Respuestas: 0 citas no verificadas (antes 1), trampas 3 de 3, longitud media 970 → 1.100 caracteres.
Latencia con la GPU libre: total 7,0 s de media (recuperación 120 ms, primer token 0,5 s). Los 17 s de
la primera prueba no se reproducen: con la GPU libre la misma pregunta tardó 3,7 s (158 tokens). Con la
GPU compartida la generación cae a 9-14 tok/s y 158 tokens son ~16 s; es la explicación más probable.

**Un error de la comprobación, no del código:** un servidor antiguo seguía vivo en el puerto 8000 y el
nuevo no arrancaba, así que las primeras respuestas de la interfaz salían con el código de antes.

### Límites conocidos

- Una cita válida sigue sin garantizar que la nota respalde la frase (comprobación de respaldo por frase:
  Fase 4).
- Copias casi idénticas con nombres distintos (`Nota`, `Nota (1)`): resuelto después en la 3b con las familias de copias.
- `3º/SISTEMAS` mezcla sistemas operativos con integración y cloud: el mapa de alias las une por pedido
  del usuario; una visión general de «sistemas operativos» incluye también esos temas.
- Ver «Pendiente para la Fase 4» (tema inventado en la visión general y formato de párrafos).
- Los umbrales (0,55 / 0,12) están calibrados con 28 preguntas; hay que revisarlos si cambia el vault.

## Fase 3b, checkpoint 1: interfaz (marco, Preguntar y Estado)

- **Diseño** (aprobado sobre `docs/design/preguntar.html`): hilo de chat con la pregunta a la derecha
  y la respuesta sin caja a 720 px de lectura; campo de pregunta flotante fijo abajo; citas
  numeradas con tooltip (CSS, nunca texto dentro del párrafo) y fila *Fuentes* con número, título corto
  y página; avisos discretos; navegación en cajón en pantallas pequeñas; «Nueva conversación» e
  historial de la sesión (la conversación vive sobre las rutas).
- **Servido por la API**: `create_app(static_dir)` sirve `frontend/dist`; las rutas del navegador
  (`/estado`) devuelven `index.html`; la API y los ficheros que faltan dan 404; no se sirve nada fuera
  de `dist` (probado con `..`, `%2e%2e` y codificaciones).
- **Pruebas**: 228 tests de interfaz (Vitest + axe por componente y página), 611 del backend
  (97 % de cobertura), `tsc`, ESLint, `ruff` y `mypy --strict` limpios.
- **Capturas y axe sobre la aplicación real** (360, 768 y 1280 px × claro y oscuro × 7 estados: inicio,
  respuesta, nota abierta, confianza baja, «no lo encuentro», error y Estado = 42): 0 violaciones y 0
  desbordes horizontales. La primera pasada encontró 3 problemas reales, ya corregidos: nombre
  accesible que no contenía el texto visible (WCAG 2.5.3), página sin `h1` y panel de nota que
  desbordaba a 768 px.
- **Límites**: las fórmulas de las notas se muestran en texto (sin KaTeX); las copias casi idénticas con
  nombre distinto se mostraban como fuentes separadas (resuelto después con las familias de copias).

## Fase 3b, checkpoint 2 (rama `feat/fase-3b-buscar-nota`, en curso)

Hecho (entregas A y B1):

- **`/search` con filtros y facetas.** `asignaturas`, `cursos` y `tags` son opcionales (MCP y el cliente
  anterior no cambian). O dentro de cada lista, Y entre listas; los nombres ignoran mayúsculas y
  acentos y usan la asignatura canónica (carpeta más alias), no el frontmatter. Las facetas cuentan
  sobre los 20 mejores candidatos sin filtrar; los valores elegidos siguen listados con 0. `/subjects`
  lista las asignaturas con su número de notas. Sobre el índice real: 220 ms sin filtros y ~300 ms con
  filtros; la primera lectura de etiquetas y enlaces tarda unos segundos y se precalienta al arrancar.
- **Pantalla Buscar**: facetas con casillas y recuentos, resultados con el fragmento sin marcas de
  Markdown y los términos resaltados (sin distinguir acentos), estado en la URL, atajos por asignatura
  y enlace desde «No lo encuentro».
- **`/notes` enriquecido**: `[[enlaces]]` resueltos por título (ruta exacta o título; copias exactas
  como una sola, la más cercana a la nota que enlaza), notas que enlazan aquí y el enlace de Obsidian.
- **Pantalla Nota** (`/nota/<ruta>`): índice de encabezados, scroll a la página (`?p=`) o al apartado
  (`#`), `[[enlaces]]` con tres estados (resuelto, ambiguo con selector, inexistente en gris),
  incrustaciones y ficheros que no son notas nombrados sin cargarse, y los encabezados del cuerpo
  recolocados bajo el título para no saltar niveles.
- **Defectos que salieron al probar con el índice real**, corregidos con test de regresión: recargar
  `/nota/…/x.md` daba 404 (la ruta acaba en `.md` y se tomaba por un fichero que falta), y dos copias
  idénticas de un resumen se resolvían siempre a la de otra asignatura.
- **Dato del vault**: de 2.994 «enlaces» solo 4 apuntan a una nota existente; el resto son conceptos
  (que no son notas) y sintaxis de shell (`[[ -f x ]]`). La función está bien pero importa poco aquí.
- Capturas y axe sobre la aplicación real (360/768/1280 px, claro y oscuro, 13 estados = 78): 0
  violaciones, 0 desbordes.

### Citas adyacentes y versiones de una nota (añadidos tras B1)

- **Citas adyacentes.** Los chips de notas distintas van separados por un espacio fino real, de modo
  que «[2][1]» se lee y se copia «2 1», no «21». Tests de texto (`answer.test.ts`, `AnswerView.test`)
  y una comprobación de maquetación en `scripts/screens.mjs` (≥ 3 px entre chips contiguos).
- **Familias de copias** (`retrieval/families.py`). Las copias exactas (mismo cuerpo) y las versiones
  (títulos que solo difieren en « (n)» o «copia»/«copy», misma asignatura canónica, contenido distinto)
  forman una familia que se muestra como una sola nota, en búsqueda, visión general y fuentes. La
  representante es la de título sin sufijo y, si no la hay, la de más fragmentos. Guardas, nacidas de
  medir sobre el índice real (la primera versión fusionaba 20 `README.md` de prácticas distintas):
  una versión solo se une al original si este es único en la asignatura, entre versiones sin original
  solo se unen las de una misma carpeta, y `(2024)` no es un sufijo. Resultado en el vault: 128
  grupos de copias exactas y 7 familias con versiones no idénticas (p. ej. `DM - Unit 5 - Classification
  - Non Rule based algorithms` y su «(1)»).
- **Golden antes/después** (28 preguntas; `evals/results/p12_*.json`): recall 0,93 → 0,93; precisión
  0,84 → 0,83; ruido 0,32 → 0,36; citas inválidas 0 → 0. La bajada de `dm-svm` es en parte de la medida: el
  evaluador busca por subcadena de título y «Unit 5 - Classification» contaba dos veces (original y
  «(1)»); ahora cuenta una y el hueco lo ocupa otra nota que pasa el corte de coseno.

### B2: fórmulas, Ctrl+K y evaluador por familias

- **Evaluador por familias.** El golden set cuenta una nota y sus copias o versiones como un único
  acierto o ruido (`score_retrieval(..., families)`), y una familia casa con una expectativa si
  cualquiera de sus miembros lo hace. Línea base buena (`evals/results/base_familias.json`) y el
  «antes» reevaluado con la misma medida: precisión total 0,83 → 0,83. `dm-svm` (ruido por una nota de
  AOC que pasa el corte de coseno) queda para la Fase 4; no se han tocado umbrales.
- **KaTeX en local.** `katex`, `remark-math` y `rehype-katex`, cargados con `import()` solo si el texto
  lleva delimitadores: el paquete principal baja de 931 KB a 660 KB y KaTeX es un chunk aparte (270 KB
  + 30 KB de CSS, fuentes en `dist/assets`). Se aplica tras el saneado, con `trust` apagado; los
  delimitadores `\( \)` y `\[ \]` de los modelos se convierten fuera del código y `$$x$$` solo en su
  línea es un bloque. El prompt pide las fórmulas en LaTeX. Se comprobó en el navegador real (fuentes
  cargadas, modo oscuro) y que no hay ninguna URL externa en `dist/`.
- **Ctrl+K / ⌘K.** Paleta con patrón combobox/listbox: acciones rápidas sin escribir, búsqueda sin LLM
  mientras se escribe (retardo de 200 ms), «Ver todos los resultados», Esc, foco devuelto al cerrar y
  foco atrapado. Hay también un botón visible en la navegación.
- **Capturas y axe**: 16 estados (96 capturas a 360/768/1280 px, claro y oscuro), 0 violaciones, 0
  desbordes y 0 chips pegados.
- **Fallo propio cazado por el lint**: el detector de fórmulas buscaba paréntesis sueltos por perder los
  backslashes al escribir el fichero desde el shell; ahora tiene un test.


## Fase 3c: modos ejercicios y apuntes (rama `feat/fase-3c-apuntes-ejercicios`)

- **Bug de citas con corchetes.** Un título con «[MD]» salía como texto crudo si la respuesta llevaba
  fórmulas: el escape `\[MD\]` del enlace de cita se leía como delimitador de bloque. La conversión de
  `\( \)`/`\[ \]` ahora respeta los enlaces de cita y solo se aplica a respuestas del modelo, no a notas
  (donde `\[` es un corchete escapado, como en Obsidian). Test de regresión con título con corchetes y
  fórmula en la misma respuesta, también en el navegador real.
- **Modo ejercicios.** Intención «ejercicios/problemas del tema N de X» (robusta a faltas y formas
  verbales), recuperación acotada a la asignatura y al tema (enunciado + solución, luego teoría), con un
  dato del índice que lista los ejercicios, contexto y tope de salida propios, y respuesta fija sin modelo
  cuando no hay ejercicios o el tema no existe. En Data Mining, tema 2: `PCA exercises 1` y
  `PCA exercises 2`, cada uno con su «solution» (y copias en IA II que las familias colapsan).
- **Regla del pipeline.** Si el modelo escribe contenido y luego «No lo encuentro en el vault», se corta
  la generación, se descarta lo escrito y se avisa («Respuesta descartada»).
- **Modo apuntes.** Plan por ventanas de fragmentos reales en orden de temario y de página, esqueleto con
  el resumen del tema, una llamada por parte con progreso, parte final de tipos de ejercicio con las notas
  de ejercicios. Medido con el modelo real: SO tema 3, 4 partes, 165 s (~48 s por parte).
  Discreta tema 5: 10 partes de teoría + ejercicios (≈ 9 min estimados; los parámetros
  `notes_window_tokens` y `notes_part_max_tokens` los acortan a costa de detalle).
- **Contexto de 16.384** para todo (decidido): el estimador de tokens infravalora el texto numérico ~1,5x,
  por eso el modo ejercicios usa un presupuesto de 7.000 estimados.
- **Guardar como nota** (`generated.py`): vista previa sin escribir, confirmación, fichero nuevo en
  `_generadas/` (exclusivo, sin sobrescribir, ruta confinada, enlaces `[[…]]` o Markdown si el título
  lleva `[ ] # ^ |`), comprobación de origen en la API y `_generadas/` fuera del índice.

### Fase 3c: correcciones tras la primera prueba del checkpoint

- **Modo ejercicios.** Se resuelve UN ejercicio completo (el que nombra la pregunta, «el ejercicio 2», o
  el primero) y se terminan listando los demás con «¿Sigo con el ejercicio N?» y cómo pedirlo (cada
  pregunta es independiente). Ya no se mezclan varios ejercicios en un contexto: el modelo se quedaba sin
  tokens y olvidaba citar. Las tablas de más de 8 filas se acortan en el contexto (el modelo las copiaba
  enteras). El prompt exige una cita por paso, copiar los resultados de la solución y no recalcular.
- **Puerta de citas.** En el golden volvió a salir una respuesta de ejercicios sin ninguna cita (el modelo
  de 7B se olvida a veces). Detectarlo no bastaba: en este modo la respuesta se genera completa, se
  comprueba que cada «Paso N» cita su fuente y, si falta alguna (o todas), se pide una vez más avisando
  de qué falló; el usuario ve solo la mejor de las dos. A cambio, en este modo no hay streaming (la
  respuesta aparece entera a los 30-55 s) y un reintento duplica el tiempo.
- **Verificación en código, no en el modelo.** Los números de una respuesta de ejercicios que no están en
  las fuentes (ni como ×100 o ÷100 de uno que sí está) se listan en un aviso («N números sin verificar»),
  y los pasos sin cita se cuentan («N pasos sin cita»). La suma 0,79209 que se inventó el modelo habría
  salido marcada. Limitación: un modelo de 7B sigue cometiendo estos fallos de vez en cuando; ahora se ven.
- **Apuntes.** El código C salía dentro de `\[ \text{…} \]` porque el prompt pedía LaTeX: KaTeX lo pintaba
  como matemáticas (texto duplicado HTML+MathML y llaves como agrupadores). Ahora el prompt exige bloques
  ``` con lenguaje y el renderizado devuelve a código todo lo que parece código dentro de delimitadores de
  fórmula (`remarkMathAsCode`). Los bloques de código con scroll son enfocables con teclado (axe). Cada
  parte puede escribir hasta 2.000 tokens y la ventana baja a 3.000 estimados, para que ninguna se corte.
- **«Abrir en Obsidian»** usa `obsidian://open?path=<ruta absoluta>`, que no depende del nombre con el que
  Obsidian tenga registrado el vault; `BRAIN_OBSIDIAN_VAULT` queda como alternativa.
- **Regla «No lo encuentro» tras contenido, variante suave.** Se conservan solo las líneas y frases con
  citas verificadas anteriores a esa frase, se añade «No he encontrado en tus apuntes el resto de lo que
  preguntas.» y la respuesta se marca como parcial. Sin ninguna frase citada se descarta entera.
- **Ambigüedad entre asignaturas** («dame la fórmula de Euler»): si entre las mejores del ranking (también
  las que el corte de coseno descarta) hay notas igual de relevantes de asignaturas distintas, el sistema
  antepone una frase fija que lo dice y responde con la más relevante. La antepone el código porque el
  modelo de 7B ignoraba la instrucción.

## Pendiente para la Fase 4

Lo que se sabe y se ha dejado a propósito para la Fase de evals, con su medida en el golden set:

1. **«Finalmente» inventado en la visión general.** Con el dato «7 temas», el modelo a veces añade un
   último tema (p. ej. «finalmente, los sistemas de machine learning…») a partir de la última fuente
   (visto en 2 de 3 ejecuciones de la misma pregunta). Medirlo: comparar los temas que lista la
   respuesta con la lista del dato; corregir con un validador posterior o con un formato más rígido.
2. **Formato de párrafos pedido.** «Un par de párrafos» pasa al modelo como instrucción explícita, pero
   el resultado fue un párrafo largo más el cierre «Destacaría:», no exactamente dos. Añadir al golden
   set una métrica de formato (nº de párrafos y ausencia de listas cuando se piden párrafos).
3. Diversificación por asignatura (prioridad 1) y comprobación de respaldo por frase (valid ≠ respaldada).
4. Orden de recuperación en preguntas concretas (p. ej. «proceso vs hilo»: recall 0,33): combinar el
   RRF con el coseno de la nota, y afinar α, cuota de notas grandes y umbral relativo.
5. ~~Copias casi idénticas con nombre distinto~~: resuelto en la 3b con las familias de copias.
6. Revisar los umbrales de relevancia (0,55 / 0,12) si cambia el vault.

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

## Siguiente paso registrado en la fase 3b

Checkpoint 2 de la 3b (Buscar y Nota): filtros y facetas en `/search`, resolución de `[[enlaces]]` por
título, «Abrir en Obsidian» y fórmulas LaTeX con KaTeX empaquetado en local. Se presenta el plan y se
espera el visto bueno antes de programar. Después, Fase 4 (evals) con lo de «Pendiente para la Fase 4».
