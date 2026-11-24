# Benchmarks reutilizables

Scripts para medir el sistema con el modelo y el índice reales. **Solo se versionan los scripts**: lo que
producen contiene texto de tus notas y va a `evals/results/`, que git ignora. Ninguno lleva nombres de tu
vault: las preguntas y los ids se pasan por argumentos.

Hace falta tener arrancados Ollama y Qdrant (`.\tasks.ps1 up`) y el índice hecho. Se ejecutan desde la
raíz del repositorio con el venv del proyecto.

| Script | Para qué |
|---|---|
| `measure_notes.py` | Modo apuntes: partes, llamadas al modelo, continuaciones, cortes sin resolver, citas y tiempo; guarda la respuesta y el texto de cada llamada. `--part-max-tokens` baja el tope de salida para provocar cortes. |
| `ab_models.py` | Compara modelos de Ollama sobre preguntas del golden (`--golden`, `--models`, `--ids`): tiempo, tokens, avisos y pico de VRAM, con semilla fija y un solo modelo cargado cada vez. |
| `reliability_browser.cjs` | Comprueba en Edge, sobre la compilación de producción (`.\tasks.ps1 web-build`), que la interfaz bloquea las imágenes remotas de una nota y no hace peticiones externas. |

```powershell
.\tasks.ps1 web-build
node evals\benchmarks\reliability_browser.cjs

C:\venvs\second-brain\Scripts\python.exe evals\benchmarks\measure_notes.py `
    --out evals\results\apuntes.json "apuntes del tema 2 de <asignatura>"

C:\venvs\second-brain\Scripts\python.exe evals\benchmarks\ab_models.py `
    --golden evals\golden\golden.local.yaml --models qwen2.5:7b qwen3:8b `
    --ids id-1 id-2 --out evals\results\ab_modelos.json
```

Los dos scripts de Python impiden que Windows suspenda el equipo mientras miden (una suspensión
falsea los tiempos y corta la conexión con Ollama).
