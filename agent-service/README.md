# agent-service

Servicio Python de flock-ai: el **Agent Worker** (responde preguntas) y el **Ingestion Worker**
(arma la base de conocimiento). Ver la sección 1.3 del [plan](../specs/001-bot-respuestas/plan.md).

## Comandos

| Qué | Comando |
|---|---|
| Instalar dependencias | `uv sync` |
| Tests | `uv run pytest` |
| Linters | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |

Los comandos `flock-agent`, `flock-ingest`, `flock-ask` y `flock-eval` se implementan en las tareas
T18, T25, T26 y T28.
