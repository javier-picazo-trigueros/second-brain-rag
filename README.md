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
.\tasks.ps1 index       # indexa el vault (Fase 1)
.\tasks.ps1 dev         # API + interfaz (Fase 3)
```

## Configuración

Copia `.env.example` a `.env` y ajusta `BRAIN_VAULT_PATH`. Los datos de Qdrant viven en el volumen
Docker `qdrant_data`, nunca en el repo. El vault se trata como solo lectura.
