# second-brain-rag

Segundo cerebro local: RAG híbrido + grafo sobre un vault de Obsidian. 100 % local (Ollama + Qdrant).
Diseño de la Fase 1 aprobado en `docs/referencia_fase1.md`; estado y decisiones en `docs/PROGRESO.md`.

## Reglas inquebrantables
1. **El vault es de solo lectura.** Nunca escribir, mover ni borrar dentro de él (salvo, en la Fase 3,
   la herramienta explícita de crear notas en `_generadas/`, aprobada por el usuario). Los tests usan
   `tests/fixtures/vault/`, jamás el vault real.
2. **Nada sale de la máquina:** sin APIs externas, sin telemetría, sin CDNs en la interfaz.
3. **TDD:** test que falla, código mínimo, refactor. Los unitarios no dependen de Ollama ni de Qdrant
   (fakes/protocolos). Los de integración llevan `@pytest.mark.integration` y se saltan si los
   servicios no responden.
4. **Calidad:** `mypy --strict` sin errores, ruff limpio, pydantic-settings para la configuración,
   `logging` en vez de `print`, sin secretos en el código, cobertura >= 85 % en `ingest/` y `retrieval/`.
5. Sin comandos destructivos ni `docker compose down -v` sin preguntar. Nada instalado globalmente.
6. Commits pequeños en formato convencional (`feat:`, `test:`, `fix:`, `refactor:`, `docs:`, `chore:`).
7. Ante un fallo: leer el error completo, explicar la causa en una línea y corregirla. Sin
   `try/except` genéricos que oculten errores.

## Git y GitHub
- Una rama por fase (`feat/fase-N-...`). Al aprobar el checkpoint: merge a `main` y push de ambas.
- Push solo al terminar un checkpoint aprobado, nunca a mitad de fase.
- Commits solo a nombre del autor (git config **local** con el correo noreply de GitHub). Sin trailers
  `Co-Authored-By`, sin "Generated with", sin menciones a una IA en commits, PR ni código.
- Antes de cada push: `git status` y `git diff --cached`. No se sube `.env`, `data/`, datos de Qdrant,
  notas del vault ni datos personales. En caso de duda, preguntar.
- El repo es público: rutas genéricas (`C:\ruta\a\tu\vault`), nada personal.

## Entorno
- Windows 11, PowerShell, Python 3.11. Ollama en el host (`http://localhost:11434`), Qdrant en Docker.
- Venv **fuera del repo** (está en OneDrive): `C:\venvs\second-brain` (o `$env:BRAIN_VENV`).
- Si un comando falla con "archivo en uso" o "access denied", suele ser OneDrive: esperar unos
  segundos y reintentar una vez; si persiste, avisar al usuario.
- GPU de 8 GB: en consulta el embedder (`bge-m3`) corre en CPU (`num_gpu=0`); LLM `qwen2.5:7b` con
  `num_ctx=16384`. Ollama con `OLLAMA_FLASH_ATTENTION=1` y `OLLAMA_KV_CACHE_TYPE=q8_0`.

## Comandos
```powershell
.\tasks.ps1 install      # venv + dependencias de desarrollo
.\tasks.ps1 test         # pytest (los de integración se saltan si no hay servicios)
.\tasks.ps1 lint         # ruff check + ruff format --check
.\tasks.ps1 typecheck    # mypy --strict
.\tasks.ps1 up           # Qdrant en Docker
.\tasks.ps1 index        # indexa el vault (brain index)
```

## Estructura
```
src/secondbrain/   config.py, domain.py, cli.py
  ingest/          parser.py, chunker.py, indexer.py, watcher.py (fase 2)
  embeddings/      ollama.py
  store/           qdrant.py, manifest.py
  retrieval/       graph.py, hybrid.py (fase 2)
  agent/, api/     (fase 3)
frontend/          React + Vite + TS + Tailwind (fase 3)
evals/             (fase 4)
tests/             unitarios + fixtures/vault/ (vault de ejemplo)
docs/              referencia_fase1.md, PROGRESO.md, architecture.md
```

## Contexto del vault (solo lectura)
~1.000 notas `.md` con frontmatter YAML (`asignatura`, `curso`, `original`, `resumen`, `tags`,
`conceptos`, `conceptos_menores`, `sin_texto`). `_conceptos/` son nodos del grafo, no se indexan como
texto. Excluir `.obsidian`, `_conceptos`, `_archivo`, `_pruebas`, `.git`, `node_modules`, `CLAUDE.md`
y `_INDICE.md`. Hay notas en español e inglés, README en UTF-16 y placeholders
`*(sin texto extraíble: ver PDF)*`.
