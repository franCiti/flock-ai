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


## Levantar el agente y preguntarle (`flock-agent` y `flock-ask`)

En contenedores: `LLM_PROVIDER=fake docker compose up -d --wait --build` levanta también el agente
(ver `infra/README.md`) y `flock-ask` se usa igual que abajo. Para correrlo en la PC:

Con el entorno de Docker Compose levantado y el conocimiento cargado. En una terminal, el Agent
Worker con su certificado y el **LLM falso** (`LLM_PROVIDER=fake`: respuestas fijas, sin API key, D41):

```powershell
$certs = (Resolve-Path infra\certs\out\agent).Path
$env:TLS_CERT_FILE = "$certs\agent.crt"; $env:TLS_KEY_FILE = "$certs\agent.key"; $env:TLS_CA_FILE = "$certs\ca.crt"
$env:POSTGRES_USER = "agent"; $env:LLM_PROVIDER = "fake"
cd agent-service; uv run flock-agent
```

En otra terminal, el cliente de prueba con el certificado `cli`:

```powershell
$certs = (Resolve-Path infra\certs\out\cli).Path
$env:TLS_CERT_FILE = "$certs\cli.crt"; $env:TLS_KEY_FILE = "$certs\cli.key"; $env:TLS_CA_FILE = "$certs\ca.crt"
$env:PYTHONIOENCODING = "utf-8"
cd agent-service; uv run flock-ask --persona juan-plataforma "¿Cómo hago un rollback?"
uv run flock-ask --persona juan-plataforma     # interactivo: una conversación, línea vacía para salir
```

Muestra la respuesta a medida que llega, sus fuentes, la persona sugerida y los tiempos. Salida:
`0` respuesta, `1` el agente respondió con un error, `2` no hubo respuesta a tiempo.
Con el modelo real (cierre de etapa) se quita `LLM_PROVIDER` y se definen `OPENROUTER_API_KEY` y `LLM_MODEL`.

## Evaluación (`flock-eval`)

Corre los casos de `eval/cases.yaml` contra el grafo (sin Kafka) sobre la base con las personas de
`examples/knowledge` (cargarlas antes con `flock-ingest run`), con el certificado del agente:

```powershell
$certs = (Resolve-Path infra\certs\out\agent).Path
$env:TLS_CERT_FILE = "$certs\agent.crt"; $env:TLS_KEY_FILE = "$certs\agent.key"; $env:TLS_CA_FILE = "$certs\ca.crt"
$env:POSTGRES_USER = "agent"; $env:PYTHONIOENCODING = "utf-8"
cd agent-service; uv run flock-eval                         # LLM_MODEL / LLM_FAST_MODEL; juez: EVAL_JUDGE_MODEL
uv run flock-eval --models modelo-a,modelo-b+modelo-rapido  # compara modelos (PRINCIPAL o PRINCIPAL+RÁPIDO)
uv run flock-eval --persona ana-datos --case ana-sales-schedule
```

Imprime el resultado de cada caso y los criterios de éxito, y escribe el reporte (Markdown y JSON,
más una comparación si hay varios modelos) en `eval/reports/` (fuera de git). Con OpenRouter **solo
al cerrar cada etapa** (D41); con `LLM_PROVIDER=fake` verifica la mecánica, no la calidad.

El comando `flock-ingest worker` se implementa en la T34.
