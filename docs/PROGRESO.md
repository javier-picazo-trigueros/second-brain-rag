# Progreso

Estado actual del proyecto y del trabajo en curso. El registro de las fases y de los checkpoints ya
cerrados está en [`HISTORIAL.md`](HISTORIAL.md).

## Estado actual

- **Publicado en `main`:** fases 0-3c, Entrega 1 (fiabilidad), Entrega 2, bloque A (continuación de las
  partes de apuntes y temas con marca corta) y Entrega 3, bloque B.
- **Último bloque cerrado:** Entrega 3, bloque B (infraestructura), integrado y publicado; el CI de GitHub
  pasa en `main`.
- **Verificación de la rama:** 1.070 pruebas del backend aprobadas (con las 35 de integración) y 1 omitida
  (symlinks en Windows), cobertura total 97 %; Vitest 419, `tsc` y ESLint en 0; ruff, `mypy --strict` y
  `.\tasks.ps1 audit` limpios.
- **Entorno:** el repositorio y `.env` están en OneDrive; el venv (`C:\venvs\second-brain`), los datos
  locales (`C:\venvs\second-brain-data`) y el volumen de Qdrant (Docker) están fuera.

## Último checkpoint cerrado · Entrega 3, bloque B (puntos 11 y 13): CI, benchmarks, historial y datos fuera de OneDrive

24 de noviembre de 2026. Aprobado, integrado en `main` y publicado.

| Punto | Resultado |
|---|---|
| CI | `.github/workflows/ci.yml`: en cada push a `main`, `feat/**` y `fix/**` y en cada PR. Job de backend (Windows, Python 3.11): ruff, formato, `mypy --strict`, pruebas unitarias (`-m "not integration"`) con cobertura de `ingest/` y `retrieval/` (mínimo 85 %; medido 99 %) y auditoría de privacidad. Job de interfaz (Ubuntu, Node 22, pnpm 10.34.9): `tsc`, ESLint y Vitest. Sin Ollama ni Qdrant. **Verificado en GitHub tras el merge:** el backend pasó a la primera; la interfaz falló porque `frontend/.npmrc` fija rutas de Windows (`C:/venvs/second-brain-web/...`) que en Linux rompen la resolución de KaTeX (12 tests); el CI borra ese `.npmrc` antes de instalar y `main` quedó en verde. |
| Auditoría sin manifest | `python -m secondbrain.privacy_audit` ya funciona sin `.env` ni correo local: sin configuración usa `data/manifest.sqlite` del repositorio y, si no existe, omite solo las comprobaciones de rutas y títulos del vault (mensaje explícito); sin correo local omite solo la autoría. El resto (datos personales, menciones a una IA en los mensajes) sigue activo. Con tests. |
| Benchmarks | `evals/benchmarks/` solo con scripts: `measure_notes.py` (apuntes), `ab_models.py` (A/B de modelos, parametrizado por modelos, ids del golden y rutas; probado con una pregunta contra Qwen2.5 7B) y `reliability_browser.cjs` (bloqueo de imágenes remotas en Edge; probado: 2 marcadores, 0 peticiones externas), más su `README.md`. No se movió nada con resultados ni con nombres reales: los experimentos puntuales de `evals/results/` (comparativa Qwen3, apuntes largos, scripts de auditoría antiguos) dependen de casos y de ids del golden local, y siguen donde estaban, ignorados por git. |
| `PROGRESO.md` / historial | `PROGRESO.md` queda con el estado actual y lo que viene; las fases y los checkpoints cerrados pasaron a [`HISTORIAL.md`](HISTORIAL.md) sin cambios de contenido. |
| `data/` fuera de OneDrive | `BRAIN_DATA_DIR` (por defecto `data/`) fija a la vez el manifest, la caché de BM25 y los alias; cada uno se puede fijar aparte y entonces manda. `brain migrate-data DESTINO` copia la carpeta (el manifest con la API de copia de SQLite, consistente aunque haya otro proceso), la **verifica** fichero a fichero (tamaño y SHA-256) y el manifest tabla a tabla, rechaza un destino con archivos, igual al origen o anidado, y no toca el origen. |

**Migración real hecha.** `data/` (978 KB: manifest de 1.000 notas y 23.236 fragmentos, 23 ficheros con la
caché de BM25 y `aliases.toml`) se copió y verificó en `C:\venvs\second-brain-data`, y se añadió
`BRAIN_DATA_DIR=C:\venvs\second-brain-data` al `.env` local. Comprobado desde la nueva ubicación:
`brain stats` (1.000 notas, 23.236 puntos), una búsqueda y `brain index` (0 cambios). **El `data/` antiguo
sigue en el repositorio, ya obsoleto** (se escribe en el nuevo): bórralo a mano cuando quieras.

**Pendiente de este bloque:** nada propio; el resto de ficheros
generados por la herramienta que vayan a `data/` en las entregas siguientes (progreso reanudable de los
apuntes, punto 10) heredarán `data_dir`.

## Último checkpoint cerrado · Entrega 2, bloque A (punto 8): continuación de partes y temas con marca corta

24 de noviembre de 2026. Aprobado, integrado en `main` y publicado.

**Continuación automática.** Una parte de apuntes que llega al tope de salida (`done_reason=length`) se
continúa con una nueva llamada que lleva las mismas fuentes y el final de lo escrito (800 caracteres), con
la orden de seguir sin repetir. Detalles:

- Hasta `BRAIN_NOTES_MAX_CONTINUATIONS` continuaciones por parte (2 por defecto; 0 las desactiva).
- Sin duplicar: se retiene el arranque de la continuación (400 caracteres) para quitar lo que repite del
  final ya escrito (solape de al menos 15 caracteres) y se empalma con un espacio o un salto de línea si el
  corte fue tras el final de una frase. Una cita cortada a medias por el tope no queda colgando.
- Dos cortes seguidos: se continúa dos veces. Si tras el límite sigue cortada, o una continuación no
  avanza (menos de 40 caracteres nuevos), la parte queda pendiente: se conserva lo escrito, no se insiste y
  sale el aviso `parte_sin_terminar` («Apuntes con una parte sin terminar», en la interfaz). El aviso
  anterior `respuesta_truncada` ya no sale en apuntes si la continuación lo resolvió.
- Citas de cada continuación verificadas con las mismas fuentes de la parte; tokens sumados.

**Temas con marca corta.** `topic_key`, `clean_title` y `topic_notes` reconocen `CAR_T2`, `T2`, `T02` y
`Tema2`/`Unit 2` (estas dos ya funcionaban), con negativos: `T20`, `T22`, `T2a`, `Part2`, `Net5`. Una sola
cifra tras la «T»: los temas de dos cifras con esa marca (T10…) no se reconocen (límite conocido; con
«Tema 10» o «Unit 10» sí).

**Medida con Qwen2.5 7B** (`evals/benchmarks/measure_notes.py`, una pasada por pregunta; la GPU estuvo
compartida con otro proceso en la primera medida de Discretas, así que sus tiempos no son comparables):

| Pregunta | | Partes | Llamadas | Continuaciones | Cortes (sin resolver) | Citas (no verificadas) | Tiempo |
|---|---|--:|--:|--:|--:|--:|--:|
| tema 2 de CAR | antes | 0 (tema no reconocido) | 0 | 0 | 0 (0) | 0 | 0,5 s |
| | después | 22 | 22 | 0 | 0 (0) | 162 (0) | 2.637 s |
| tema 5 de Discretas | antes | 13 | 13 | 0 | 0 (0) | 125 (0) | 7.268 s (GPU compartida) |
| | después | 13 | 12 | 0 | 0 (0) | 120 (0) | 1.947 s |
| tema 2 de Data Mining | antes | 9 | 9 | 0 | 0 (0) | 101 (0) | 871 s |
| | después | 9 | 10 | 1 | 1 (0) | 101 (0) | 1.388 s |

Lectura honesta: los cortes son raros con el tope de 2.000 tokens (1 en 44 partes, como ya se vio en la
3c), así que la continuación se ejerció una vez con el modelo real (DM, resuelta) y el resto con modelo
simulado. CAR pasó de «no encuentro» a 22 partes de apuntes con 162 citas válidas. En la pasada «después»
de Discretas el modelo escribió contenido y luego «No lo encuentro» en una parte (`respuesta_contradictoria`,
esa parte se descartó; no salió en la pasada «antes»): es variación del modelo, no de este cambio. Los
tiempos de «después» (GPU compartida a ratos) no deben leerse como coste de la continuación. No revisé a
mano el texto de la continuación real de DM (el script no guarda las respuestas).

Verificación: 1.045 pruebas del backend aprobadas (con las 35 de integración) y 1 omitida (symlinks),
cobertura total 97 %; Vitest 419, `tsc` y ESLint en 0; ruff, `mypy --strict` y auditoría de privacidad
limpios. En una pasada con cobertura apareció un «1 error» de pytest que no se reprodujo en dos pasadas
posteriores (no se identificó la causa). Los tests de este bloque se reescribieron antes de publicar con
nombres ficticios (filtro local sobre la rama, `main` intacta).

### Revisión del bloque A (24 de noviembre)

- **«1 error» intermitente de pytest: reproducido y explicado.** Diez vueltas de los 223 tests de
  concurrencia, publicación, watcher, API y catálogo con cobertura: 0 fallos. Una pasada completa
  (1.045 pruebas) con Vitest ×3 en paralelo: verde la primera vez y, la segunda, 5 errores en
  `tests/integration/test_end_to_end.py`, todos de su fixture: `ResponseHandlingException: timed out` en
  `PUT /collections/<prueba>/index?wait=true`. No es una carrera de datos: el cliente de Qdrant usaba su
  plazo por defecto (5 s) y, con la máquina cargada, crear los índices lo supera. Arreglo con test:
  `BRAIN_QDRANT_TIMEOUT_S` (30 s por defecto, también para publicar). Es la causa más probable del error
  original, pero esa primera pasada no guardó el detalle: no está demostrado que fuera el mismo test.
- **Suspensión del equipo.** Durante la noche el PC se suspendió (eventos de energía a las 00:54, 03:29 y
  10:36): una vuelta del bucle marcó 9 h 45 min y una medición se cayó al perder la conexión con Ollama.
  `measure_notes.py` ahora impide la suspensión mientras mide (`SetThreadExecutionState`).
- **GPU.** Con `nvidia-smi` ahora: 0 % y 0 MiB, sin procesos. Durante las mediciones de la víspera la GPU
  iba al 100 % con otro proceso: un `python.exe` de un entorno de `uv` (PID 2736, arrancado a las 19:28 del
  23 de noviembre, línea de órdenes `… -u src/spp/methods_v04/blo…`, no es de este proyecto). Ya no existe,
  así que no pude ver desde dónde se lanzó ni su directorio de trabajo. No lo paré. Explica los tiempos
  altos de la primera medida de Discretas; es la causa observada, no probada.
- **Empalme de la continuación, revisado a mano con el modelo real** (`--part-max-tokens 700` para forzar
  cortes: 17 llamadas, 8 continuaciones). Fallaba en la mayoría de los empalmes: el modelo, al continuar,
  suele **empezar una frase nueva** en vez de seguir la cortada. Salían palabras pegadas
  («…has far fewerRandom under-sampling…», «…subsetsRandom…»), un `**` colgando seguido del encabezado
  repetido (`### Feature aggregation` dos veces) y elementos de lista sin salto de línea. Corregido con
  tests de esos casos: se retiene el final de cada llamada (400 caracteres) por si se corta; el empalme
  quita el solape aunque el corte dejara marcas colgando, separa con el salto que corresponde (párrafo,
  lista, título) y, si lo cortado era una frase a medias y lo siguiente es una frase nueva, descarta la
  frase a medias (si no hay frontera en esos 400 caracteres la conserva marcada con « […]»). Si lo que sigue
  continúa en minúscula, se une tal cual. Nueva medición con el modelo real (19 llamadas, 10
  continuaciones, 12 cortes, 2 sin resolver): 0 palabras pegadas (la única coincidencia es «DataFrame»),
  0 títulos repetidos seguidos, 0 marcas colgando, frente a 3 palabras pegadas antes. Siguen los defectos
  del propio modelo, que la continuación no puede arreglar: cita el encabezado de las fuentes
  («### [S55] Nota: …») y una tabla cortada por el tope queda cortada (parte sin terminar, con aviso).
  El punto débil restante es descartar una frase a medias: se pierde lo que el modelo había escrito en ella.

## Siguiente

Puntos a planificar, de [`revision-2026-11-19.md`](revision-2026-11-19.md): 9 (golden ampliado con
calibración y evaluación separadas, y comprobación de respaldo por frase), 10 (apuntes por apartados con
progreso reanudable en la carpeta de datos) y 12 (perfiles de modelo por modo, tras el golden). Siguen
también los pendientes de la Fase 4 y de la fase 3c que lista ese documento. Se decide el orden con tu OK.
