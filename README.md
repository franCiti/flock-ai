# flock-ai

Bot que responde preguntas con el conocimiento de un empleado: sus documentos, correos, issues y
páginas. Cada empleado se representa con una **persona virtual** con su propia base de conocimiento.
El bot es un servicio que cualquier aplicación consume por Kafka; incluye una interfaz web de demostración.

> **Estado:** en construcción — etapa 1 (núcleo). Ver el avance en
> [specs/001-bot-respuestas/tasks.md](specs/001-bot-respuestas/tasks.md).

## Documentación

- [Especificación](specs/001-bot-respuestas/spec.md) — qué hace el bot.
- [Plan técnico](specs/001-bot-respuestas/plan.md) — cómo se construye.
- [Backlog](specs/001-bot-respuestas/tasks.md) — tareas y estado.
- [Decisiones](docs/decisiones.md) · [Arquitectura](docs/arquitectura.md) · [Notas del entorno](docs/notas-entorno.md)

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python y sus dependencias)
- Docker Desktop
- Java 21 y Node.js (a partir de la etapa 2)

## Primeros pasos

1. Copiar la configuración y completar los secretos:

   ```bash
   cp .env.example .env
   ```

2. Instalar pre-commit y activar los hooks (una sola vez por clon):

   ```bash
   uv tool install pre-commit
   pre-commit install
   ```

3. Verificar que todo pasa:

   ```bash
   scripts/check.sh
   ```

## Estructura

| Carpeta | Contenido |
|---|---|
| `contracts/` | Contrato público del agente (AsyncAPI + JSON Schema) |
| `agent-service/` | Python: agente e ingesta |
| `core-api/` | Java: backend de la interfaz web |
| `web/` | React: interfaz web |
| `infra/` | Docker Compose, certificados, Kafka y Postgres |
| `examples/` | Personas ficticias para desarrollo y evaluación |
| `docs/`, `specs/` | Documentación y artefactos de SDD |
