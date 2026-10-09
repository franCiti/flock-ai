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
- Marca `integration_containers`: levantan un PostgreSQL efímero con **Testcontainers** (misma imagen
  y mismo script de roles que el entorno real) para probar la lógica sobre tablas. Requieren Docker;
  sin Docker se omiten. Ryuk está desactivado (falla en Docker Desktop para Windows): los contenedores
  se detienen al terminar la sesión de tests.

## Migraciones

- Cada dueño de schema aplica las suyas al arrancar (`common/migrations.py`, yoyo): las de
  `knowledge` están en `src/flock_agent/knowledge/migrations/`.
- Una migración que use tipos de pgvector debe empezar con `SET LOCAL search_path = <schema>, public;`
  (yoyo deja el `search_path` solo en el schema que migra).

## Notas

- **Windows:** el modo asíncrono de psycopg no funciona con el event loop por defecto de Windows.
  Los comandos usan `common.aio.run_async()` y los tests el hook equivalente de `tests/conftest.py`.
- **TLS interno vs. internet:** `bootstrap()` inyecta `truststore` (certificados del sistema) para
  las conexiones a internet; las conexiones internas usan un contexto propio que confía solo en la
  CA de flock-ai (`common/tls.py`).

## Actualizar la base de conocimiento a mano (`flock-ingest run`)

Contra el entorno de Docker Compose, con el certificado de la ingesta (PowerShell, desde la raíz del repo):

```powershell
$certs = (Resolve-Path infra\certs\out\ingestion).Path
$env:TLS_CERT_FILE = "$certs\ingestion.crt"; $env:TLS_KEY_FILE = "$certs\ingestion.key"; $env:TLS_CA_FILE = "$certs\ca.crt"
$env:POSTGRES_USER = "ingestion"; $env:KNOWLEDGE_ROOT = (Resolve-Path examples\knowledge).Path
cd agent-service; uv run flock-ingest run              # o --persona juan-plataforma
```

Aplica las migraciones pendientes, procesa las carpetas e imprime el resumen por persona. Salida:
`0` bien, `1` falló, `3` ya había otra actualización en curso.

Pendiente: ocultar secretos (T12) y leer correos (T14) están marcados como `TODO` en el código.

Los comandos `flock-ingest worker`, `flock-agent`, `flock-ask` y `flock-eval` se implementan en las
tareas T34, T25, T26 y T28.
