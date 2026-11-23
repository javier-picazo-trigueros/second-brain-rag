# second-brain-rag

Segundo cerebro local: RAG híbrido + grafo sobre un vault de Obsidian. 100 % local (Ollama + Qdrant).

> Trabajo en curso. El README completo (arquitectura, evals, limitaciones) llega al final del proyecto.

## Requisitos

- Windows 11, PowerShell, Python 3.11, Docker Desktop.
- Ollama en el host con `qwen2.5:7b` y `bge-m3` (`ollama pull qwen2.5:7b`, `ollama pull bge-m3`).
- Variables de Ollama: `OLLAMA_FLASH_ATTENTION=1` y `OLLAMA_KV_CACHE_TYPE=q8_0`.

## Entorno de Python

El entorno virtual vive **fuera del repo** (el proyecto está en OneDrive): `C:\venvs\second-brain`.

```powershell
.\tasks.ps1 install          # crea el venv si no existe e instala el proyecto con extras de desarrollo
C:\venvs\second-brain\Scripts\Activate.ps1   # activarlo en la sesión (opcional: tasks.ps1 no lo necesita)
```

Para usar otra ruta: `$env:BRAIN_VENV = "D:\venvs\brain"`.

## Tareas

```powershell
.\tasks.ps1 test        # pytest
.\tasks.ps1 lint        # ruff check + ruff format --check
.\tasks.ps1 typecheck   # mypy --strict
.\tasks.ps1 up          # levanta Qdrant (Docker)
.\tasks.ps1 index       # indexa el vault
.\tasks.ps1 watch       # sincroniza y vigila el vault
.\tasks.ps1 serve       # API HTTP en http://127.0.0.1:8000
.\tasks.ps1 dev         # API + interfaz en modo desarrollo
.\tasks.ps1 web-install # dependencias de la interfaz (pnpm)
.\tasks.ps1 web-build   # compila la interfaz en frontend\dist
.\tasks.ps1 web-test    # tests de la interfaz (Vitest)
```

## Uso

```powershell
brain index                        # indexa el vault (solo lo nuevo o cambiado)
brain search "iptables" -k 5       # búsqueda híbrida; añade --no-graph para quitar las relacionadas
brain graph "Nombre de la nota"    # conceptos y notas conectadas por el grafo
brain watch                        # mantiene el índice al día mientras editas el vault
brain serve                        # API HTTP (solo en localhost)
brain stats
```

Con el embedder en GPU la ingesta masiva va más rápido (`BRAIN_EMBED_ON_CPU=false`); en consulta
(API y MCP) el embedder va siempre en CPU para dejar la VRAM al modelo de lenguaje.

## API HTTP

`brain serve` arranca FastAPI en `127.0.0.1:8000` (documentación interactiva en `/docs`). Se niega a
escuchar fuera de la máquina salvo que se pase `--allow-remote`, porque no tiene autenticación, y
rechaza peticiones con una cabecera `Host` que no sea local.

| Endpoint | Qué hace |
|---|---|
| `GET /health` | Estado de Ollama (modelos instalados y cargados, VRAM), Qdrant, vault y GPU, con pistas de cómo arreglarlo |
| `GET /stats` | Notas, chunks, copias exactas, conceptos y última sincronización |
| `POST /search` | Búsqueda híbrida: una entrada por nota, copias exactas colapsadas y notas relacionadas por el grafo |
| `POST /ask` | Respuesta en streaming (SSE) con citas verificadas |
| `GET /notes/{ruta}` | Contenido, metadatos y vecinas de una nota indexada |
| `GET /graph/neighbors/{ruta}` | Conceptos de la nota (con idf) y sus vecinas |
| `POST /reindex`, `GET /reindex/status` | Reindexado en segundo plano, de uno en uno, con progreso |

`/ask` emite los eventos `sources` (las notas que el modelo podrá citar), `token` (texto ya
verificado), `done` (citas, avisos, confianza, tiempos y tokens) o `error`.

### Cómo se responde y qué garantiza

1. Se detecta la intención de la pregunta, escrita como se habla («de q va», «q se da», «cuantos
   temas tiene», sin tildes, con faltas y con relleno). Si pide una **visión general** de una
   asignatura o de un «tema N», no se buscan fragmentos: se resumen las notas de esa asignatura o tema
   con su `resumen`, sus conceptos y sus apartados. Quedan fuera los libros (las «notas grandes»), las
   guías docentes y, si hay un temario numerado (`Unit N`, `Tema N`), todo lo que no sea temario. El
   **número de temas sale del índice** (unidades distintas por nombre de archivo) y se le pasa al
   modelo como dato exacto; si la pregunta pide «un par de párrafos» u otro número, se le da como
   instrucción explícita. Si nombra dos asignaturas, se busca en cada una y se intercalan los
   resultados. En cualquier otro caso, búsqueda híbrida normal.
2. Solo pasan como evidencia las notas parecidas a la pregunta: el coseno de su mejor fragmento debe
   llegar a `BRAIN_MIN_NOTE_COSINE` (0,55) y no quedar más de `BRAIN_COSINE_MARGIN` (0,12) por debajo
   del mejor. Si ninguna pasa, la respuesta es «No lo encuentro en el vault.» sin llamar al modelo.
3. Con ellas se arma un contexto con presupuesto de tokens (4.500 de los 8.192 de `num_ctx`; se estima
   con 3 caracteres por token). Cada fragmento lleva un identificador corto: `[S1]`, `[S2]`…
4. `qwen2.5:7b` responde solo con ese contexto y cita con esos identificadores. El título y la página
   que se muestran son los del fragmento, los pone el sistema: el modelo no puede inventarlos.
5. Cada cita se comprueba mientras llega el texto: un identificador que no está en el contexto se
   sustituye por `[cita no verificada: S9]`.
6. Si el contexto no basta, el modelo debe responder exactamente «No lo encuentro en el vault.».

#### Alias de asignaturas

La asignatura de una nota es su carpeta de segundo nivel (`curso/ASIGNATURA/...`); cada carpeta
funciona sola con su nombre. Para que «Data Mining» o «matemática discreta» lleguen a las carpetas
`DM` o `Discretas`, copia `docs/aliases.example.toml` a `data/aliases.toml` (esa carpeta está ignorada
por git) y ajústalo a tu vault. Cambiar el fichero no requiere reindexar. Los alias se comparan como
palabra completa (`car` no coincide dentro de «carácter») y toleran una falta en las palabras largas;
los números y las palabras cortas deben coincidir exactos. Un `include` mueve la nota a esa asignatura.

**Limitaciones conocidas.** Verificar una cita garantiza que la nota y la página **existen en el
contexto**, no que respalden la afirmación: un modelo de 7B puede extrapolar y citar con formato
correcto (se ha visto). La señal `confidence` (coseno denso del mejor chunk, umbral 0,60 calibrado con
27 preguntas) es un aviso, no un bloqueo: separa mal los temas ausentes más cercanos. En preguntas que
cruzan asignaturas, la recuperación puede traer evidencia de una sola; ver `docs/PROGRESO.md`.

## Interfaz web

React + Vite + TypeScript + Tailwind, 100 % local (fuentes incluidas en el repo, sin CDN ni telemetría).
Pantallas: **Preguntar** (hilo de conversación, citas numeradas, fuentes, avisos), **Buscar**
(búsqueda sin modelo, con filtros por asignatura, curso y etiqueta; O dentro de cada filtro e Y entre
ellos, con recuentos; el estado va en la URL), **Nota** (la nota completa: índice de encabezados,
`[[enlaces]]` resueltos por título, notas que la enlazan y «Abrir en Obsidian») y **Estado**
(servicios, GPU, índice, reindexado y latencia de la sesión).

**Fórmulas.** Las notas y las respuestas del modelo muestran LaTeX (`$x^2$`, `$$...$$`, y también
`\(...\)` y `\[...\]`) con KaTeX, empaquetado en local (fuentes incluidas, sin CDN) y cargado solo la
primera vez que aparece una fórmula. Va con `trust` apagado: sin `\href`, `\url` ni imágenes remotas.

**Ctrl+K** (⌘K en Mac) abre una paleta para saltar a una pantalla, empezar una conversación o buscar
una nota sin salir de donde estás. Es un cuadro de diálogo accesible con teclado completo.

**Modo ejercicios.** «Resuélveme los ejercicios del tema 2 de data mining paso a paso» busca solo en
esa asignatura y ese tema: primero los enunciados (cada uno con su solución, si existe) y después la
teoría del tema para justificar los pasos. Si el tema no tiene ejercicios lo dice sin llamar al modelo y
lista lo que sí tiene.

**Modo apuntes.** «Hazme unos apuntes del tema 5 de discreta» (o «explícame en detalle el tema 5…»)
recorre los fragmentos reales de las notas de teoría del tema, en orden de página, y escribe los
apuntes por partes (definiciones, teoremas con su enunciado, ejemplos, fórmulas en LaTeX y una última
parte de «Tipos de ejercicio»). Cada parte lleva sus citas; se ve el progreso («Parte 3 de 7») y se puede
parar conservando lo escrito. Tarda del orden de 45 s por parte con la GPU libre.

**Guardar como nota.** Al terminar, «Guardar como nota» enseña la ruta y el contenido exactos y, solo
si lo confirmas, crea un `.md` nuevo en `_generadas/` del vault (con asignatura, tema, fecha y fuentes
como enlaces). Es la única escritura que se hace en el vault: nunca sobrescribe (añade « (2)»), no sale
de `_generadas/`, solo acepta peticiones del propio origen y esa carpeta no se reindexa.

«Abrir en Obsidian» es un enlace `obsidian://open?path=<ruta absoluta>` que construye la API; no
ejecuta nada ni escribe en el vault. Si prefieres abrir por el nombre con el que Obsidian conoce el
vault, define `BRAIN_OBSIDIAN_VAULT` y usará `obsidian://open?vault=…&file=…`.
Un `[[enlace]]` con varias notas candidatas pregunta cuál se quiere; las copias exactas cuentan como
una y se elige la más cercana a la nota que enlaza.

```powershell
.\tasks.ps1 web-install   # una vez
.\tasks.ps1 web-build     # compila frontend\dist
.\tasks.ps1 serve         # la API sirve también la interfaz: http://127.0.0.1:8000
```

Para desarrollar con recarga en caliente: `.\tasks.ps1 dev` (API en :8000 y Vite en :5173, que
reenvía las peticiones a la API).

**Cómo se ve cada respuesta.** Las citas son números discretos (`1`, `2`…) junto a la frase; el título
y la página salen al pasar el ratón o enfocar, y en móvil, tocar el número abre la nota. Bajo la
respuesta, la fila *Fuentes* repite cada número con el título corto de la nota y su página. Los avisos
(confianza baja, citas no verificadas) son píldoras tenues; solo un servicio caído usa el rojo. «No lo
encuentro en tus apuntes» es una tarjeta serena con las notas más cercanas.

**pnpm y `node_modules` fuera de OneDrive.** El repo vive en OneDrive, que sincronizaría decenas de
miles de ficheros de `node_modules`. La interfaz usa pnpm: su almacén y su almacén virtual están en
`C:\venvs\second-brain-web` (ver `frontend/.npmrc`) y `node_modules` solo contiene enlaces. No
ejecutes `npm install` en `frontend/`: sustituiría esos enlaces por una carpeta real dentro de OneDrive.
`frontend/pnpm-workspace.yaml` lista, con versión exacta, los paquetes publicados hace pocos días que
se permitieron saltándose la antigüedad mínima de pnpm (`typescript-eslint` y sus subpaquetes,
`axe-core` y `@testing-library/user-event`).

**Comprobaciones manuales** (no forman parte de los tests; escriben fuera del repo):

```powershell
cd frontend
node scripts/screens.mjs <carpeta>   # 42 capturas (360/768/1280 px, claro y oscuro) + axe de cada una
node scripts/ask-ui.mjs <carpeta> "una pregunta"   # pregunta en la interfaz real y mide
```

Usan el Edge instalado (`BRAIN_BROWSER` para otro navegador). La propuesta de diseño estática está en
`docs/design/preguntar.html`.

## Servidor MCP (Claude Code y otros clientes)

`python -m secondbrain.mcp_server` es un servidor MCP por stdio, de solo lectura, con tres
herramientas: `search_notes`, `get_note` (por tramos, con tope de caracteres) y `related_notes`.
Necesita Qdrant (`.\tasks.ps1 up`) y Ollama arrancados. Funciona lance quien lo lance, desde cualquier
directorio: el `.env` y `data/` se resuelven desde la raíz del proyecto.

Para registrarlo en Claude Code:

```powershell
claude mcp add second-brain --scope user -- C:\venvs\second-brain\Scripts\python.exe -m secondbrain.mcp_server
claude mcp list
```

`--scope user` lo deja disponible en todos tus proyectos; con `--scope project` se guarda en el
`.mcp.json` del proyecto actual.

> **Privacidad: lo que devuelven estas herramientas sale de tu máquina.** El proyecto es 100 % local,
> pero cuando un cliente como Claude Code llama a `search_notes` o `get_note`, el texto de tus notas
> pasa a la conversación y se envía al servicio del cliente (en Claude Code, a la API de Anthropic).
> Es inherente a conectarlo. Para limitarlo: las salidas están acotadas (`BRAIN_MCP_SNIPPET_CHARS`,
> `BRAIN_MCP_MAX_CHARS`), las herramientas son de solo lectura y puedes dejar notas sensibles fuera del
> índice con `BRAIN_EXCLUDE_GLOBS` (ver `.env.example`). Solo conéctalo a clientes en los que confíes
> con esas notas. La API HTTP y la CLI no envían nada fuera.

## Evaluación (preguntas de referencia)

`evals/golden/` contiene el formato de un conjunto de preguntas con las notas que deberían
recuperarse (`golden.example.yaml`, ficticio). Copia el ejemplo a `golden.local.yaml` (ignorado por
git, porque lleva nombres de tu vault) y ejecuta:

```powershell
brain golden run --out evals/results/antes.json            # solo recuperación (rápido, sin GPU)
brain golden run --answers --out evals/results/despues.json  # además genera las respuestas
brain golden compare evals/results/antes.json evals/results/despues.json
```

Mide recall, precisión, notas de ruido y top-1 por tipo de pregunta (concreta, visión general de una
asignatura o tema, cruzada, trampa). Con `--answers` añade longitud, citas no verificadas y latencias,
y anota el estado de la GPU: si está compartida con otro proceso, las latencias no son comparables.

## Configuración

Copia `.env.example` a `.env` y ajusta `BRAIN_VAULT_PATH`. Los datos de Qdrant viven en el volumen
Docker `qdrant_data`, nunca en el repo. El vault se trata como solo lectura.

## Licencia

Este proyecto se distribuye bajo la [PolyForm Noncommercial License 1.0.0](LICENSE). Se puede ver,
usar y modificar con fines no comerciales. Para cualquier uso comercial, contacta con el autor,
Javier Picazo Trigueros.
