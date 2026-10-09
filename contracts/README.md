# contracts

Contrato de mensajería del agente: es la **fuente de verdad** de los mensajes que viajan por Kafka
(plan, secciones 1.2 y 2; decisiones D23 y D33). Los archivos del contrato están en inglés porque
son código.

| Archivo | Contenido |
|---|---|
| `asyncapi.yaml` | Canales (tópicos), operaciones y mensajes, en AsyncAPI 3.0 |
| `schemas/*.v1.json` | Un JSON Schema (draft-07) por mensaje |
| `examples/<mensaje>/*.json` | Ejemplos válidos de cada mensaje |
| `docs/` | Documentación HTML generada (fuera de git) |

## Reglas

- **API pública:** `agent.requests` y `agent.replies.<clientId>`. Los cambios incompatibles requieren
  una versión nueva (`.v2`), nunca se modifica una versión publicada de forma incompatible.
- Agregar un campo **opcional** es compatible: los consumidores ignoran los campos desconocidos.
- Todo mensaje nuevo o modificado lleva ejemplos en `examples/`.

## Después de cambiar un esquema

1. Regenerar los modelos de Python:

   ```bash
   cd agent-service && uv run python scripts/generate_contracts.py
   ```

2. Correr los tests: validan los ejemplos contra los esquemas y fallan si el código generado
   quedó desactualizado.

   ```bash
   cd agent-service && uv run pytest tests/unit/test_contracts.py
   ```

3. Las clases de Java se regeneran solas en cada build de `core-api` (a partir de la T30).

## Documentación

Valida el documento AsyncAPI y genera `docs/index.html` (requiere Node.js):

```bash
contracts/build-docs.sh
```
