# agent-service

Servicio Python de flock-ai: el **Agent Worker** (responde preguntas) y el **Ingestion Worker**
(arma la base de conocimiento). Ver la sección 1.3 del [plan](../specs/001-bot-respuestas/plan.md).

## Comandos

| Qué | Comando |
|---|---|
| Instalar dependencias | `uv sync` |
| Tests | `uv run pytest` |
| Solo tests unitarios | `uv run pytest tests/unit` |
| Linters | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |
| Regenerar los modelos del contrato | `uv run python scripts/generate_contracts.py` |

## Tests de integración

- `tests/integration/` con la marca `integration_stack`: se conectan al entorno de Docker Compose
  (`localhost:5433` y `localhost:9093`) con los certificados de `infra/certs/out/`. Si el entorno no
  está levantado se **omiten** y lo indican. Para correrlos:

  ```bash
  docker compose up -d --wait
  ```

- No dejan rastro: las tablas de prueba se borran al terminar y Kafka se lee sin grupo de
  consumidores, así no se mueven los offsets de los servicios.

## Notas

- **Windows:** el modo asíncrono de psycopg no funciona con el event loop por defecto de Windows.
  Los comandos usan `common.aio.run_async()` y los tests el hook equivalente de `tests/conftest.py`.
- **TLS interno vs. internet:** `bootstrap()` inyecta `truststore` (certificados del sistema) para
  las conexiones a internet; las conexiones internas usan un contexto propio que confía solo en la
  CA de flock-ai (`common/tls.py`).

Los comandos `flock-agent`, `flock-ingest`, `flock-ask` y `flock-eval` se implementan en las tareas
T18, T25, T26 y T28.
