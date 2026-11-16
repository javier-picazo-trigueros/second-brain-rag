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
.\tasks.ps1 dev         # API + interfaz (Fase 3b)
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

1. Se recuperan notas con la búsqueda híbrida y se arma un contexto con un presupuesto de tokens
   (4.500 de los 8.192 de `num_ctx`; se estima con 3 caracteres por token, que sobreestima 9-21 %).
2. `qwen2.5:7b` responde solo con ese contexto y debe citar `[[Nombre de la nota]]` y `(p. N)`.
3. Cada cita se comprueba mientras llega el texto: una nota que no está en el contexto se sustituye por
   `[cita no verificada: X]` y una página que no está en el contexto se marca `(p. N no verificada)`.
4. Si el contexto no basta, el modelo debe responder exactamente «No lo encuentro en el vault.».

**Limitaciones conocidas.** Verificar una cita garantiza que la nota y la página **existen en el
contexto**, no que respalden la afirmación: un modelo de 7B puede extrapolar y citar con formato
correcto (se ha visto). La señal `confidence` (coseno denso del mejor chunk, umbral 0,60 calibrado con
27 preguntas) es un aviso, no un bloqueo: separa mal los temas ausentes más cercanos. En preguntas que
cruzan asignaturas, la recuperación puede traer evidencia de una sola; ver `docs/PROGRESO.md`.

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

## Configuración

Copia `.env.example` a `.env` y ajusta `BRAIN_VAULT_PATH`. Los datos de Qdrant viven en el volumen
Docker `qdrant_data`, nunca en el repo. El vault se trata como solo lectura.

## Licencia

Este proyecto se distribuye bajo la [PolyForm Noncommercial License 1.0.0](LICENSE). Se puede ver,
usar y modificar con fines no comerciales. Para cualquier uso comercial, contacta con el autor,
Javier Picazo Trigueros.
