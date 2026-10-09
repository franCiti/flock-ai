# Plan técnico: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** Aprobado (2026-10-09, Francisco Neyrotte)
**Spec:** [spec.md](spec.md) (aprobada) · **Decisiones:** [docs/decisiones.md](../../docs/decisiones.md)

> El plan describe **cómo** se construye lo que pide la spec. Cada pieza indica qué historias
> (`HUxx`) cubre y qué decisiones (`Dxx`) aplica. Todo el código, nombres de archivos,
> paquetes y configuración van en **inglés** (D02).

## Índice

1. [Estructura del repositorio y de los servicios](#1-estructura-del-repositorio-y-de-los-servicios)
2. [Contrato AsyncAPI](#2-contrato-asyncapi)
3. [Modelo de datos](#3-modelo-de-datos)
4. [Grafo del agente](#4-grafo-del-agente)
5. [Ingesta y conectores](#5-ingesta-y-conectores)
6. [Core API y front](#6-core-api-y-front)
7. [Seguridad e infraestructura](#7-seguridad-e-infraestructura)
8. [Tests y evaluación](#8-tests-y-evaluación)
9. [Riesgos y mapa de cobertura de la spec](#9-riesgos-y-mapa-de-cobertura-de-la-spec)

---

## 1. Estructura del repositorio y de los servicios

### 1.1 Raíz del monorepo (D35)

```
flock-ai/
├── CLAUDE.md                 project conventions for Claude Code (language rules, linters, SDD)
├── README.md                 how to run everything
├── .editorconfig             shared editor settings (indent, charset, final newline)
├── .pre-commit-config.yaml   all linters, for every language (D03)
├── .env.example              every env var, empty secrets; copied to .env (gitignored)
├── .gitignore  .gitattributes
├── contracts/                public agent contract (D23, D33)
├── agent-service/            Python: agent worker + ingestion worker
├── core-api/                 Java: backend for the web app
├── web/                      React: chat, sources admin, audit log
├── infra/                    Docker Compose, CA and certificates, Kafka ACLs
├── data/                     runtime data, gitignored (knowledge folders)
├── examples/                 sample knowledge and personas for dev and evaluation
├── docs/
└── specs/
```

- **Comando único de calidad:** `pre-commit run --all-files` ejecuta todos los linters de todos los
  lenguajes; los mismos hooks corren antes de cada commit. Pre-commit se instala con
  `uv tool install pre-commit` (instalación del usuario y permanente: el hook de git guarda la ruta de
  su Python, así que no sirve un entorno temporal como el de `uvx`).
- **`CLAUDE.md`:** deja escritas las reglas del proyecto (idiomas, linters, SDD) para que cualquier
  sesión de Claude Code las respete sin depender de la memoria de una conversación.

### 1.2 `contracts/` — contrato público del agente (D33)

```
contracts/
├── asyncapi.yaml             channels (topics), operations and messages
├── schemas/                  JSON Schema, one file per message
│   ├── agent-request.v1.json
│   ├── agent-reply.v1.json   accepted, token, final, error (discriminated by "type")
│   ├── ingestion-job.v1.json
│   ├── ingestion-event.v1.json
│   └── audit-entry.v1.json
└── docs/                     generated HTML documentation (gitignored, built on demand)
```

- Es la **fuente de verdad**: Java y Python **generan** sus clases a partir de estos esquemas,
  en lugar de escribirlas a mano. Si el contrato cambia, el código que no lo respeta no compila
  o no pasa los tests.
  - Python: modelos Pydantic generados con `datamodel-code-generator`.
  - Java: clases generadas con `jsonschema2pojo` (plugin de Maven) en cada build.
- El versionado va en el nombre del esquema (`.v1`) y en el campo `version` del mensaje (D23).
- El detalle de los mensajes se define en la sección 2.

### 1.3 `agent-service/` — Python (D06)

Un solo proyecto uv con **dos procesos** que comparten código: el **agente** y la **ingesta**.

```
agent-service/
├── pyproject.toml            dependencies, ruff and mypy config, entry points
├── uv.toml                   system-certs = true (corporate proxy, see docs/notas-entorno.md)
├── config/
│   └── messages.yaml         configurable bot messages, in Spanish (HU11)
├── src/flock_agent/
│   ├── common/               shared infrastructure
│   │   ├── settings.py         typed settings from env vars (pydantic-settings)
│   │   ├── logging.py
│   │   ├── tls.py              mTLS contexts for Kafka and Postgres (D17)
│   │   ├── db.py               Postgres connection pool
│   │   └── kafka.py            producer/consumer helpers
│   ├── contracts/            models generated from contracts/schemas (do not edit)
│   ├── knowledge/            shared by agent and ingestion
│   │   ├── models.py           SourceDocument, Chunk, Persona
│   │   ├── repository.py       documents, chunks, personas (schema "knowledge")
│   │   ├── embeddings.py       Embedder interface + local implementation (D22)
│   │   ├── chunking.py
│   │   └── redaction.py        secret detection and masking (HU15)
│   ├── ingestion/
│   │   ├── connectors/
│   │   │   ├── base.py           SourceConnector interface (D19)
│   │   │   ├── files/            FileStore (local, SharePoint) + parsers (D20)
│   │   │   ├── jira.py           via MCP (D30)
│   │   │   └── confluence.py     via MCP (D30)
│   │   ├── mcp_client.py       shared MCP client setup
│   │   ├── personas.py         persona folders and profile files (HU9)
│   │   ├── pipeline.py         sync: changes → redaction → chunks → embeddings → store
│   │   ├── worker.py           consumes ingestion.jobs, publishes ingestion.events (D31)
│   │   └── cli.py              manual run for development
│   ├── agent/
│   │   ├── graph/              LangGraph state, nodes and graph assembly (section 4)
│   │   ├── prompts/            system prompts (English)
│   │   ├── llm.py              OpenRouter chat model factory (D08)
│   │   ├── fake_llm.py         fake chat model: tests and development runs without API key (D41)
│   │   ├── messages.py         loads config/messages.yaml (HU11)
│   │   ├── guardrails.py       input limits, injection signals (HU15)
│   │   ├── rate_limit.py       requests per minute per client app (HU15)
│   │   ├── conversations.py    retention by last message (HU5)
│   │   ├── audit.py            audit log (HU8)
│   │   └── worker.py           consumes agent.requests, streams to replyTo (D24)
│   └── tools/
│       ├── ask.py              CLI test client: sends a question over Kafka, prints the reply
│       └── evaluate.py         evaluation runner (section 8)
├── eval/                     evaluation datasets (questions, expected answers, attacks)
└── tests/
    ├── unit/
    └── integration/          real Kafka and Postgres (Docker)
```

**Entry points** (comandos que instala el proyecto):

| Comando | Qué hace |
|---|---|
| `flock-agent` | Levanta el Agent Worker |
| `flock-ingest worker` | Levanta el Ingestion Worker (escucha `ingestion.jobs`) |
| `flock-ingest run [--persona X]` | Ejecuta una ingesta manual (desarrollo, HU4) |
| `flock-ask` | Cliente de prueba por línea de comandos (D27) |
| `flock-eval` | Corre el set de evaluación contra un modelo (D38) |

**Dependencias principales:**

| Necesidad | Librería |
|---|---|
| Grafo del agente | `langgraph` + `langgraph-checkpoint-postgres` |
| LLM vía OpenRouter | `langchain-openai` (`ChatOpenAI` apuntando a la URL de OpenRouter) |
| Kafka | `aiokafka` (asíncrono, soporta mTLS) |
| Postgres + vectores | `psycopg` 3 + `pgvector` |
| Embeddings locales | `fastembed` |
| MCP | `mcp` (SDK oficial) + `langchain-mcp-adapters` |
| Configuración y validación | `pydantic`, `pydantic-settings` |
| Parsers | `pypdf`, `python-docx`, `extract-msg` (.msg), `email` de la librería estándar (.eml), `charset-normalizer` (detectar archivos de texto por contenido) |
| Certificados del proxy corporativo | `truststore` |
| Calidad | `ruff`, `mypy`, `pytest` |

**Por qué asíncrono:** el worker atiende muchas conversaciones a la vez y casi todo su tiempo es
espera (LLM, Kafka, base). Con `asyncio` un solo proceso maneja muchas respuestas en streaming sin hilos.

### 1.4 `core-api/` — Java (D05, D36)

Un proyecto Maven de un solo módulo, organizado **por funcionalidad** (no por capa técnica):

```
core-api/
├── pom.xml                   Spring Boot, springdoc, Spotless, Checkstyle, jsonschema2pojo
└── src/
    ├── main/java/ar/com/flockit/flockai/core/
    │   ├── CoreApiApplication.java
    │   ├── auth/              Spring Security, login, users table (D16)
    │   ├── persona/           personas available to the UI (HU10)
    │   ├── source/            external sources admin: CRUD, credentials (HU12)
    │   ├── ingestion/         scheduler + manual trigger → ingestion.jobs (D31)
    │   ├── chat/              REST + SSE for the web, Kafka client of the agent (HU10)
    │   ├── audit/             audit log queries for the web (HU8)
    │   ├── kafka/             Kafka config (mTLS), topics
    │   └── common/            errors, config properties
    ├── main/resources/
    │   ├── application.yml
    │   └── db/migration/      Flyway migrations, schema "core"
    └── test/java/...          JUnit 5 + Testcontainers (D38)
```

- **Paquete base:** `ar.com.flockit.flockai.core`.
- **Migraciones de base:** Flyway, solo sobre el schema `core` (D12).
- **Documentación:** springdoc genera OpenAPI y publica Swagger UI en `/docs/swagger-ui` (D32).
- **Clases del contrato:** generadas desde `contracts/schemas` en cada build (sección 1.2).
- **Personas y auditoría:** viven en schemas de Python; Java las recibe por Kafka y guarda copias
  de lectura (sección 3.5).

### 1.5 `web/` — React + TypeScript (D10)

```
web/
├── package.json  vite.config.ts  tsconfig.json  eslint.config.js  .prettierrc
└── src/
    ├── main.tsx  App.tsx  routes.tsx
    ├── api/               typed client generated from the Core API OpenAPI spec
    ├── features/
    │   ├── auth/          login page (HU10)
    │   ├── chat/          persona picker, streaming answer, sources, countdown (HU6, HU10)
    │   ├── sources/       external sources admin + "update now" (HU12, D31)
    │   └── audit/         filterable audit log (HU8)
    ├── components/        shared UI components
    └── styles/            Flock design tokens (.claude/skills/flock-design-system)
```

- **Build:** Vite. **Gestor de paquetes:** npm.
- **Cliente de la API:** se genera desde el OpenAPI de la Core API (`openapi-typescript`), así el
  front no escribe a mano los tipos de las respuestas.
- **Respuestas del bot:** se muestran como Markdown **sin HTML** y sin cargar recursos externos (HU15).

### 1.6 `infra/` (D17, D25, D37)

```
infra/
├── docker-compose.yml       kafka (KRaft), postgres+pgvector, agent, ingestion, core-api, web
├── certs/
│   ├── generate.sh          creates the dev CA and one certificate per service
│   └── out/                 generated certificates and keys (gitignored)
├── kafka/
│   └── acls.sh              topic creation and ACLs per client certificate (D25)
└── postgres/
    └── init.sql             schemas, roles per service, certificate auth (D12, D17)
```

- Los certificados se generan con OpenSSL **dentro de un contenedor**, así no hace falta instalar
  nada en Windows. La sección 7 detalla la CA, los certificados por servicio y las ACLs.

### 1.7 Datos de ejemplo y conocimiento

```
data/knowledge/              real knowledge root (gitignored), one folder per persona (D29)
└── juan-plataforma/
    ├── persona.md           profile: display name + external identities (HU9)
    └── ...                  any supported file (HU4)

examples/knowledge/          fictional personas versioned in the repo, used by dev and evaluation
```

- El perfil `persona.md` usa **frontmatter YAML** (datos estructurados al inicio de un Markdown):

  ```markdown
  ---
  display_name: Juan Pérez
  identities:
    email: juan.perez@example.com
  ---
  Free notes for the operator (not used as knowledge).
  ```
- La carpeta raíz del conocimiento es configurable; por defecto, `data/knowledge`.

### 1.8 Configuración

Todo lo configurable de la spec se resuelve con **variables de entorno** (documentadas en
`.env.example`), excepto los mensajes, que van en `config/messages.yaml`:

| Parámetro | Variable | Defecto | Spec |
|---|---|---|---|
| Retención de conversaciones | `CONVERSATION_TTL` | `1d` | HU5 |
| Tiempo máximo de respuesta | `ANSWER_TIMEOUT` | `2m` | HU6 |
| Objetivo del primer fragmento | `FIRST_TOKEN_TARGET` | `10s` | RNF |
| Intervalo de ingesta | `INGESTION_INTERVAL` | `30m` | HU4 |
| Largo máximo de pregunta | `MAX_QUESTION_CHARS` | `2000` | HU15 |
| Pedidos por minuto por app | `MAX_REQUESTS_PER_MINUTE` | `30` | HU15 |
| Modelo del LLM | `LLM_MODEL` | *se define con la evaluación* | D08 |
| API key de OpenRouter | `OPENROUTER_API_KEY` | *vacío* | D08 |
| Carpeta raíz de conocimiento | `KNOWLEDGE_ROOT` | `data/knowledge` | D29 |
| Archivo de mensajes | `MESSAGES_FILE` | `agent-service/config/messages.yaml` | HU11 |

> `MAX_REQUESTS_PER_MINUTE = 30` es un valor inicial propuesto; la spec no fija un número.

---

## 2. Contrato AsyncAPI

Cubre: HU1, HU2, HU5, HU6, HU7, HU13, HU14, HU15 · Aplica: D09, D11, D23, D24, D25, D31, D33

### 2.1 Identidad de la app cliente

Se mantiene D24 tal como está: un único `agent.requests` y el campo `replyTo` en cada pedido.

- **Kafka no le dice al consumidor quién publicó un mensaje**: el agente toma el `clientId` del
  nombre del tópico indicado en `replyTo` (`agent.replies.<clientId>`). Es un dato **declarado** por
  la app, no verificado; se usa para el límite de pedidos por minuto y la auditoría (HU8, HU15).
- Las ACLs (D25) siguen controlando quién puede publicar en `agent.requests` y quién puede leer
  cada `agent.replies.<clientId>`.
- **Riesgo aceptado:** una app autorizada podría declarar el `replyTo` de otra. Se acepta para el MVP
  porque todas las apps cliente son internas y autorizadas.

### 2.2 Tópicos

| Tópico | Tipo | Mensaje | Clave | Spec |
|---|---|---|---|---|
| `agent.requests` | **Público** | `AgentRequest` | `conversationId` | HU1, HU7 |
| `agent.replies.<clientId>` | **Público** | `AgentReply` | `conversationId` | HU6, HU7 |
| `ingestion.jobs` | Interno | `IngestionJob` | `jobId` | HU4, HU12 |
| `ingestion.events` | Interno | `IngestionEvent` | `jobId` | HU4, HU12 |
| `agent.audit` | Interno | `AuditEntry` | `requestId` | HU8 (ver 3.5) |

- **Público** = forma parte de la API del agente: cambios incompatibles solo con una versión nueva (D23).
- **Interno** = solo lo usan nuestros servicios; igual se documenta en el AsyncAPI.
- La clave `conversationId` mantiene en orden los mensajes de una misma conversación (misma partición).

**Convenciones de todos los mensajes:**
- JSON en UTF-8, nombres de campos en `camelCase`, fechas en ISO 8601 UTC, identificadores generados como UUID.
- Campo `version` obligatorio (hoy, `1`).
- Headers de Kafka: `content-type: application/json` y `schema: <nombre>.v<versión>`.
- Los campos desconocidos se **ignoran** (así se pueden agregar campos opcionales sin romper a nadie).

### 2.3 `AgentRequest` — pedido de una app cliente

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `version` | `1` | sí | Versión del contrato |
| `requestId` | UUID | sí | Identifica el pedido. Un `requestId` repetido **no se procesa dos veces** (caso borde de la spec) |
| `conversationId` | string (1–128) | sí | Lo genera la app. Agrupa preguntas de una misma conversación (HU5) |
| `personaId` | string (`^[a-z0-9][a-z0-9-]{0,62}$`) | sí | A qué persona virtual se le pregunta (nombre de su carpeta) |
| `question` | string (≥ 1) | sí | La pregunta. El largo máximo lo valida el agente según configuración (HU15) |
| `replyTo` | string (`^agent\.replies\.[a-z0-9-]{1,64}$`) | sí | Tópico donde la app quiere las respuestas; de ahí sale su `clientId` (2.1) |
| `sentAt` | fecha | sí | Cuándo la envió la app |
| `clientContext` | objeto `string → string` (≤ 10 pares) | no | Datos libres de la app; el agente los **devuelve** en cada respuesta, sin interpretarlos |

```json
{
  "version": 1,
  "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
  "conversationId": "web-session-42",
  "personaId": "juan-plataforma",
  "question": "¿Cómo hago rollback de un deploy?",
  "replyTo": "agent.replies.core-api",
  "sentAt": "2026-10-09T15:20:00Z",
  "clientContext": { "uiMessageId": "m-17" }
}
```

### 2.4 `AgentReply` — mensajes de respuesta

Un pedido produce **varios** mensajes `AgentReply`, distinguidos por el campo `type`:

```
accepted ──> token ──> token ──> … ──> final
    │  
    └──────────────(en cualquier punto)──> error
```

**Garantías:**
1. Todo pedido termina con **exactamente un** mensaje terminal: `final` o `error`.
2. `seq` empieza en 0 y crece de a 1 dentro de cada pedido: permite ordenar y detectar faltantes.
3. El texto de `final.answer` es el **definitivo**: la app reemplaza lo que armó con los `token`.
4. Un pedido inválido igual recibe un `error` si se pudo leer su `replyTo`; los campos que no se
   pudieron leer llegan en `null`. Si ni siquiera hay un `replyTo` válido, el pedido se descarta y
   queda registrado en la auditoría.

**Campos comunes a todos los tipos:**

| Campo | Tipo | Descripción |
|---|---|---|
| `version` | `1` | Versión del contrato |
| `type` | `accepted` \| `token` \| `final` \| `error` | Tipo de mensaje |
| `requestId` | UUID o `null` | El del pedido (`null` solo en errores de pedidos ilegibles) |
| `conversationId` | string o `null` | El del pedido |
| `personaId` | string o `null` | El del pedido |
| `seq` | entero ≥ 0 | Orden dentro del pedido |
| `sentAt` | fecha | Cuándo lo emitió el agente |
| `clientContext` | objeto | El que mandó la app, sin cambios |

**`accepted`** — el agente tomó el pedido.

| Campo | Descripción |
|---|---|
| `deadlineAt` | Hasta cuándo puede llegar la respuesta (`ANSWER_TIMEOUT`). El front lo usa para la **cuenta regresiva** (HU10) |

**`token`** — fragmento de la respuesta en curso (HU6).

| Campo | Descripción |
|---|---|
| `text` | Texto nuevo a agregar. Agrupa los tokens generados en ~100 ms (D11) |

**`final`** — respuesta completa (HU1, HU2, HU13, HU14).

| Campo | Descripción |
|---|---|
| `answer` | Respuesta completa en Markdown, en el idioma de la pregunta |
| `outcome` | Qué tipo de respuesta es (ver tabla siguiente) |
| `persona` | `{ id, displayName }` de la persona que respondió |
| `citations` | Lista de fuentes usadas (vacía si no aplica) |
| `referral` | `{ personaId, displayName }` si sugiere preguntarle a otra persona (HU2); si no, `null` |
| `timing` | `{ firstTokenMs, totalMs }` para medir el objetivo de 10 s del primer fragmento |

| `outcome` | Cuándo | Spec |
|---|---|---|
| `answered` | Respondió con fuentes | HU1 |
| `partially_answered` | Respondió una parte y aclara qué no encontró | HU2.5 |
| `no_information` | No tiene la información (puede incluir `referral`) | HU2, HU14 |
| `out_of_scope` | Pedido ajeno a la base y al ámbito laboral | HU14 |
| `small_talk` | Saludo, agradecimiento o despedida | HU14 |
| `about_assistant` | Preguntó quién es o qué hace | HU13 |

Cada elemento de `citations`:

| Campo | Descripción |
|---|---|
| `documentId` | Identificador estable del documento en la base |
| `title` | Título legible |
| `url` | Enlace al original (issue de Jira, página de Confluence, archivo de SharePoint); `null` para archivos de las carpetas (5.9) |
| `path` | Ruta relativa del archivo dentro de la carpeta de la persona (solo archivos de carpetas) |
| `section` | Sección o encabezado, si se conoce (opcional) |
| `sourceType` | `file` \| `email` \| `email_attachment` \| `jira` \| `confluence` \| `sharepoint` |

```json
{
  "version": 1, "type": "final", "seq": 42,
  "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
  "conversationId": "web-session-42", "personaId": "juan-plataforma",
  "sentAt": "2026-10-09T15:20:07Z", "clientContext": { "uiMessageId": "m-17" },
  "answer": "Soy el asistente virtual de Juan Pérez. Para hacer rollback…",
  "outcome": "answered",
  "persona": { "id": "juan-plataforma", "displayName": "Juan Pérez" },
  "citations": [{
    "documentId": "files:juan-plataforma:procedures/deploy.md",
    "title": "Deploy a producción", "section": "Rollback",
    "url": null, "path": "procedures/deploy.md", "sourceType": "file"
  }],
  "referral": null,
  "timing": { "firstTokenMs": 2310, "totalMs": 6980 }
}
```

**`error`** — el pedido terminó sin respuesta.

| Campo | Descripción |
|---|---|
| `code` | Código estable, para que la app decida qué hacer |
| `message` | Texto para mostrar, desde `messages.yaml`, en el idioma de la pregunta si se conoce (HU11) |
| `retryable` | Si tiene sentido reintentar el mismo pedido más tarde |

| `code` | Cuándo | `retryable` | Spec |
|---|---|---|---|
| `INVALID_REQUEST` | No cumple el esquema | no | Casos borde |
| `UNSUPPORTED_VERSION` | `version` desconocida | no | Casos borde |
| `PERSONA_NOT_FOUND` | La persona no existe | no | HU3 |
| `QUESTION_TOO_LONG` | Supera `MAX_QUESTION_CHARS` | no | HU15 |
| `RATE_LIMITED` | La app superó sus pedidos por minuto | sí | HU15 |
| `TIMEOUT` | Se superó `ANSWER_TIMEOUT` | sí | HU6 |
| `LLM_UNAVAILABLE` | El modelo no respondió | sí | Casos borde |
| `INTERNAL_ERROR` | Cualquier otro error | sí | HU6 |

### 2.5 `IngestionJob` — pedido de actualización (interno)

| Campo | Tipo | Descripción |
|---|---|---|
| `version` | `1` | |
| `jobId` | UUID | |
| `trigger` | `scheduled` \| `manual` | Programado (cada 30 min) o desde la interfaz (D31) |
| `requestedAt` | fecha | |
| `sources` | lista | **Todas** las fuentes externas configuradas, de todas las personas (ver 3.6) |

Cada fuente: `{ sourceId, personaId, type, scope }`, donde `type` es `jira` \| `confluence` \|
`sharepoint` y `scope` indica qué parte tomar (clave de proyecto, clave de espacio, sitio + carpeta).
Las carpetas de todas las personas se recorren siempre.

- La Core API es dueña de las fuentes (D31), así que **las manda en el pedido**: el Ingestion
  Worker no necesita consultarle nada a Java.
- **El mensaje no lleva credenciales** (ver pregunta abierta 2).

### 2.6 `IngestionEvent` — avance y resultado (interno)

| `type` | Cuándo | Datos |
|---|---|---|
| `started` | Empezó la actualización | — |
| `rejected` | Ya había una en curso (HU4.9) | `reason` |
| `persona_completed` | Terminó una persona | Resumen de la persona (ver abajo) |
| `persona_removed` | Se borró la carpeta de una persona | `personaId` |
| `completed` | Terminó todo | Totales |
| `failed` | Falló la actualización completa | `reason` |

Resumen por persona (HU4.5, HU9, HU12.8, HU15.4): `personaId`, `displayName`, cantidades de
`added`, `modified`, `deleted`, `unchanged`, `secretsMasked`, y la lista de `skipped`
(`{ path, reason }`) y de `sourceErrors` (`{ sourceId, reason }`).

### 2.7 Documentación generada

- `contracts/asyncapi.yaml` usa **AsyncAPI 3.0** y referencia los JSON Schema de `contracts/schemas/`.
- La documentación HTML se genera con el generador oficial de AsyncAPI (ejecutado en un
  contenedor) y se sirve junto con la Core API, al lado de Swagger UI.
- Un test valida que los ejemplos de esta sección cumplen los esquemas.

### 2.8 Credenciales de las fuentes externas (D39)

Cada sistema (Jira, Confluence, SharePoint) se lee con **una cuenta de servicio**, cuyas credenciales
están en la configuración del Ingestion Worker (`.env`). El filtro por autor (D30) garantiza que de
cada persona se toma solo lo suyo. Las credenciales nunca viajan por Kafka ni se guardan en la base,
y la interfaz no las maneja (spec HU12.6, ajustada).

## 3. Modelo de datos

Cubre: HU2, HU3, HU4, HU5, HU8, HU9, HU10, HU12, HU15 · Aplica: D12, D16, D18, D26, D31

### 3.1 Dueños y acceso (precisión de D12)

Una sola instancia de Postgres con tres schemas. Cada servicio se conecta con **su propio rol**
(autenticado por certificado, sección 7) que solo tiene los permisos mínimos:

| Schema | Dueño | Rol | Permisos |
|---|---|---|---|
| `knowledge` | agent-service | `ingestion` | lectura y escritura |
| `knowledge` | agent-service | `agent` | **solo lectura** |
| `agent` | agent-service | `agent` | lectura y escritura |
| `core` | core-api | `core_api` | lectura y escritura |

- `knowledge` y `agent` pertenecen al mismo proyecto Python (D35), pero la ingesta y el agente son
  procesos distintos: el agente **no puede modificar** la base de conocimiento.
- Java no tiene acceso a `knowledge` ni a `agent`. Lo que necesita mostrar en el front le llega por
  Kafka y lo guarda en **copias de lectura** en `core` (3.4).

### 3.2 Schema `knowledge` — base de conocimiento

```
persona 1───* document 1───* chunk
   │              │
   │              └── parent_id (adjuntos de correos → su correo)
   └───* sync_state

ingestion_run        meta
```

**`persona`** — una por carpeta (HU9).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | text PK | Nombre de la carpeta (`juan-plataforma`) |
| `display_name` | text | Del perfil `persona.md` |
| `identities` | jsonb | `{ "email": "…" }`, para el filtro por autor (D30) |
| `profile_hash` | text | Para detectar cambios en el perfil |
| `created_at`, `updated_at` | timestamptz | |

Si la carpeta de una persona desaparece, se borra la persona y, en cascada, todo su conocimiento.

**`document`** — cada archivo, correo, adjunto, issue o página.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | text PK | Estable entre actualizaciones: `file:<persona>:<ruta>`, `jira:<persona>:<issueKey>`… |
| `persona_id` | FK → persona | `ON DELETE CASCADE` |
| `source_type` | text | `file` \| `email` \| `email_attachment` \| `jira` \| `confluence` \| `sharepoint` |
| `source_id` | text, nullable | La fuente externa de la que vino (`null` = carpeta de la persona) |
| `parent_id` | FK → document, nullable | Adjunto → su correo (HU4) |
| `title`, `url`, `section_hint` | text | Para las citas |
| `source_updated_at` | timestamptz | Fecha de modificación en el origen |
| `content_hash` | text | Si no cambió, no se reprocesa (HU4.4) |
| `secrets_masked` | int | Cuántos secretos se ocultaron (HU15.4) |
| `indexed_at` | timestamptz | |

**`chunk`** — los fragmentos que se buscan.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | bigserial PK | |
| `document_id` | FK → document | `ON DELETE CASCADE` |
| `persona_id` | text | Repetido a propósito: toda búsqueda filtra por persona sin un join (HU3) |
| `ordinal` | int | Orden dentro del documento |
| `heading_path` | text | "Deploy > Rollback", para citar la sección |
| `content` | text | Texto ya **sin secretos** |
| `embedding` | `vector(N)` | N lo fija el modelo de embeddings (384 con el actual) |
| `tsv` | tsvector (generada) | Búsqueda por palabras exactas (nombres de jobs, códigos de error); se combina con la vectorial en la sección 4 |

Índices: HNSW sobre `embedding` (similitud coseno), GIN sobre `tsv`, B-tree sobre `persona_id`.

**`sync_state`** — dónde quedó cada sincronización incremental.

| Columna | Tipo | Nota |
|---|---|---|
| `persona_id`, `source_key` | PK compuesta | `source_key` = `folder` o el `sourceId` externo |
| `cursor` | jsonb | Opaco para el pipeline; cada conector guarda lo suyo |
| `last_synced_at` | timestamptz | |

**`ingestion_run`** — historial de actualizaciones (HU4.5).

| Columna | Tipo | Nota |
|---|---|---|
| `job_id` | uuid PK | El del `IngestionJob` |
| `trigger` | text | `scheduled` \| `manual` |
| `status` | text | `running` \| `completed` \| `failed` \| `rejected` |
| `started_at`, `finished_at` | timestamptz | |
| `summary` | jsonb | El resumen por persona que también viaja en `IngestionEvent` |

**`meta`** — clave/valor. Guarda el modelo de embeddings con el que se indexó la base; si cambia,
la siguiente actualización **reindexa todo** (los vectores de modelos distintos no son comparables).

**Reglas de consistencia:**
- **Reemplazo atómico por documento:** borrar sus chunks e insertar los nuevos ocurre en **una
  transacción**. Quien busca ve la versión anterior completa o la nueva completa, nunca una mezcla
  (caso borde de la spec).
- **Nunca dos actualizaciones a la vez** (HU4.9): un *advisory lock* de Postgres (un candado a nivel
  base de datos). Si está tomado, el job se rechaza con `IngestionEvent.rejected`.

### 3.3 Schema `agent` — conversaciones, idempotencia y auditoría

**Checkpoints de LangGraph** — tablas creadas y administradas por `langgraph-checkpoint-postgres`.
Guardan el estado de cada conversación (HU5). Cada conversación es un *thread* de LangGraph.

**`conversation`** — controla la retención (HU5.3).

| Columna | Tipo | Nota |
|---|---|---|
| `client_id`, `conversation_id` | PK compuesta | Dos apps pueden usar el mismo `conversationId` sin mezclarse |
| `persona_id` | text | |
| `generation` | int | Sube cuando la conversación expira o cambia de persona |
| `last_message_at` | timestamptz | |

- El *thread* de LangGraph es `<clientId>:<conversationId>:<generation>`.
- Si pasó más de `CONVERSATION_TTL` desde `last_message_at`, **o** el pedido es para otra persona,
  sube `generation`: la conversación empieza sin historial.
- Una tarea periódica del agente borra los checkpoints de conversaciones vencidas.

**`processed_request`** — idempotencia (caso borde: pedido repetido).

| Columna | Tipo | Nota |
|---|---|---|
| `request_id` | uuid PK | Si ya existe, el pedido se ignora |
| `client_id` | text | |
| `received_at` | timestamptz | Se borran pasados 7 días |

**`rate_limit_window`** — pedidos por minuto por app (HU15.5).

| Columna | Tipo | Nota |
|---|---|---|
| `client_id`, `window_start` | PK compuesta | Ventana de un minuto |
| `request_count` | int | Se incrementa con un upsert atómico |

Va en la base, y no en memoria, para que el límite sea correcto aunque haya varios Agent Workers.

**`audit_entry`** — registro de lo respondido (HU8, HU15.7).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | uuid PK | |
| `request_id`, `client_id`, `conversation_id`, `persona_id` | | Pueden ser `null` en pedidos ilegibles |
| `question`, `answer` | text | |
| `outcome` | text | El `outcome` del `final`, o `error` |
| `error_code` | text, nullable | |
| `citations` | jsonb | |
| `referral_persona_id` | text, nullable | Derivación sugerida (HU2) |
| `flags` | text[] | `injection_suspected`, `rate_limited`, `question_too_long`, `invalid_request` |
| `llm_model` | text | Con qué modelo se respondió (para comparar, D08) |
| `prompt_version` | text | Versión de los prompts usados (4.6) |
| `first_token_ms`, `total_ms` | int | Objetivo de 10 s (RNF) |
| `created_at` | timestamptz | |

Índices: `(persona_id, created_at)`, `(created_at)` y GIN sobre `flags`, para los filtros de la interfaz (HU8.2).

### 3.4 Schema `core` — Core API (Flyway)

| Tabla | Contenido | Spec |
|---|---|---|
| `app_user` | `id`, `username` (único), `password_hash` (BCrypt), `enabled`, `created_at` | HU10, D16 |
| `source` | `id`, `persona_id`, `type`, `scope` (jsonb), `created_at`, `updated_at` | HU12 |
| `persona_view` | Copia de lectura: `id`, `display_name`, `updated_at` | HU10, HU12 |
| `ingestion_run_view` | Copia de lectura: estado y resumen de cada actualización | HU4, HU12 |
| `audit_entry_view` | Copia de lectura del registro de auditoría | HU8 |

- **Usuario inicial:** si `app_user` está vacía al arrancar, la Core API crea el usuario con
  `ADMIN_USERNAME` y `ADMIN_PASSWORD` (variables de entorno). La contraseña nunca se guarda en texto plano.
- **Sesiones:** en memoria de la Core API (una sola instancia en el MVP). Si se reinicia, hay que
  volver a iniciar sesión.

### 3.5 Cómo se llenan las copias de lectura de Java

Resuelve el pendiente de la sección 1.4. Los datos de Python le llegan a Java **por Kafka**:

| Copia en `core` | Se alimenta de | Mensaje |
|---|---|---|
| `persona_view` | `ingestion.events` | `persona_completed` (alta o cambio) y `persona_removed` (baja) |
| `ingestion_run_view` | `ingestion.events` | Todos los tipos |
| `audit_entry_view` | `agent.audit` (**tópico nuevo**, interno) | `AuditEntry`: el mismo contenido que `audit_entry` |

- Así se respeta D12: nadie lee tablas ajenas.
- `agent.audit` contiene preguntas y respuestas: sus ACLs solo permiten escribir al Agent Worker y
  leer a la Core API.
- **Alternativa descartada:** que Java lea con un rol de solo lectura las tablas de Python.
  Es más simple, pero acopla a Java con el modelo interno de Python.

### 3.6 Cambios que esta sección introduce en la sección 2

1. **Tópico nuevo `agent.audit`** con el mensaje `AuditEntry` (interno, clave `requestId`).
2. **`IngestionEvent` suma `persona_removed`** y el `displayName` en `persona_completed` (ya estaba).
3. **`IngestionJob` lleva la lista completa de fuentes externas**, no solo las de algunas personas.
   Así la ingesta sabe qué fuentes se quitaron: borra los documentos cuyo `source_id` ya no está
   en la lista (HU12.4). Las carpetas de todas las personas se recorren siempre.

## 4. Grafo del agente

Cubre: HU1, HU2, HU3, HU5, HU6, HU11, HU13, HU14, HU15 · Aplica: D07, D08, D11, D22, D26

### 4.1 Recorrido completo de un pedido

El trabajo se divide en dos partes: el **worker** hace las validaciones baratas y deterministas
(sin LLM) y el **grafo** de LangGraph hace el razonamiento.

```
agent.requests
     │
     v
┌─────────────────────────── Worker (sin LLM) ───────────────────────────┐
│ 1. validar contra el esquema ───────────────────> error INVALID_REQUEST │
│ 2. ¿requestId ya procesado? ────────────────────> se ignora            │
│ 3. límite por app ──────────────────────────────> error RATE_LIMITED    │
│ 4. largo de la pregunta ────────────────────────> error QUESTION_TOO_LONG│
│ 5. ¿existe la persona? ─────────────────────────> error PERSONA_NOT_FOUND│
│ 6. resolver conversación (retención, cambio de persona)                 │
│ 7. publicar accepted { deadlineAt }                                     │
│ 8. ejecutar el grafo con tiempo límite ─────────> error TIMEOUT          │
│ 9. publicar final o error                                               │
│10. registrar auditoría (tabla + agent.audit)                            │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Todos los rechazos de 1 a 5 se auditan con su flag** (HU15.7) y no consumen LLM.
- **Concurrencia:** el worker procesa varios pedidos a la vez (límite configurable), pero los de una
  **misma conversación** van de a uno y en orden.
- **Entrega "al menos una vez":** el offset de Kafka se confirma recién después de publicar la
  respuesta. Si el worker se cae a mitad de camino, el pedido se reprocesa; la idempotencia del paso 2
  evita respuestas duplicadas de pedidos ya terminados.

### 4.2 El grafo

```
            START
              │
              v
       ┌─────────────┐
       │ screen_input│  señales de inyección (reglas, sin LLM)
       └──────┬──────┘
              v
       ┌─────────────┐
       │  classify   │  LLM, salida estructurada
       └──────┬──────┘
   ┌──────────┼─────────────────────┐
   │ question │ small_talk          │
   v          │ about_assistant     │
┌──────────┐  │ out_of_scope        │
│ retrieve │  v                     │
└────┬─────┘ ┌──────────────┐       │
     v       │ canned_reply │<──────┼───────────────┐
┌──────────┐ └──────┬───────┘       │               │
│  grade   │        │               │               │
└────┬─────┘        │               │               │
     │ suficiente      parcial      │ nada          │
     │                    │         v               │
     │                    │  ┌───────────────┐      │
     │                    └─>│ find_referral │──────┘ (no_information
     │                       └──────┬────────┘          ± referral)
     │      parcial ± referral      │
     v<─────────────────────────────┘
┌──────────┐
│ generate │
└────┬─────┘
     v
┌──────────┐
│ finalize │<──── (canned_reply también termina acá)
└────┬─────┘
     v
    END
```

**Estado del grafo:** historial de la conversación, pregunta, persona (`id`, `displayName`), idioma,
intención, consulta reformulada, fragmentos recuperados, veredicto, respuesta, `outcome`, citas,
derivación y flags.

### 4.3 Nodos

**`screen_input`** — sin LLM (HU15.1).
Busca patrones conocidos de manipulación ("ignorá tus instrucciones", "ignore previous instructions",
"system prompt", "actuá como", etc.). **No bloquea**: solo marca el flag `injection_suspected` para la
auditoría. La defensa real está en el diseño de los demás nodos (4.5).

**`classify`** — una llamada al LLM con **salida estructurada** (JSON validado por esquema).
Devuelve en una sola llamada:

| Campo | Para qué |
|---|---|
| `language` | Idioma de la pregunta (HU1.4) |
| `intent` | `question` \| `small_talk` \| `about_assistant` \| `out_of_scope` |
| `standalone_query` | La pregunta reescrita para que se entienda sola, usando el historial (HU5): "¿y si sale mal?" → "¿qué hago si un deploy sale mal?" |
| `manipulation_attempt` | Si el pedido intenta cambiar el comportamiento del bot (flag, HU15.7) |

Ante la duda, `intent` es `question`: es preferible buscar y no encontrar que rechazar una pregunta válida.

**`retrieve`** — sin LLM. **Búsqueda híbrida** en los fragmentos de **esa persona** (HU3):
1. Búsqueda vectorial: los 20 fragmentos más similares a `standalone_query`.
2. Búsqueda por palabras: los 20 mejores por texto exacto (columna `tsv`, sección 3.2).
3. Se combinan con **Reciprocal Rank Fusion** (suma puntajes según la posición en cada lista) y se
   quedan los 8 mejores.

La búsqueda por palabras complementa a la vectorial donde esta falla: nombres de jobs, códigos de
error, siglas.

**`grade`** — LLM con salida estructurada. Evalúa si los fragmentos responden la pregunta:

| Campo | Para qué |
|---|---|
| `verdict` | `sufficient` \| `partial` \| `none` |
| `relevant_ids` | Qué fragmentos sirven |
| `missing` | Qué parte no está cubierta (si `partial`) |

Separar la evaluación de la generación tiene tres ventajas: el `outcome` sale de una decisión
explícita y no de interpretar el texto; el generador solo ve los fragmentos **relevantes** (menos
superficie para inyecciones); y es medible por separado en la evaluación.

**`generate`** — LLM en **streaming** (HU6). Recibe solo los fragmentos relevantes, numerados.
Responde en el idioma de la pregunta, marca las fuentes como `[1]`, `[2]` y, si el veredicto fue
`partial`, aclara qué no encontró (HU2.5). Los tokens se publican agrupados cada ~100 ms (D11).

**`find_referral`** — sin LLM para buscar, con LLM para confirmar (HU2.2–2.4).
Se ejecuta cuando `grade` da `none` y también cuando da `partial`; en ese caso busca a alguien para
**la parte que falta** (`missing`), y `generate` responde lo que tiene y suma la sugerencia al final.
1. Busca `standalone_query` (o `missing`, si fue parcial) en los fragmentos de **todas las demás** personas.
2. Agrupa por persona y toma la de mejor puntaje, si supera un umbral mínimo configurable.
3. Una llamada corta al LLM confirma si ese contenido responde la pregunta.
4. Si confirma, la derivación es `{ personaId, displayName }`. **El contenido de la otra persona
   nunca pasa al texto de la respuesta**: solo se usa para decidir (HU2.3).

**`canned_reply`** — mensajes de `messages.yaml` (HU11, HU13, HU14).
Toma la plantilla que corresponde (`about_assistant`, `small_talk`, `out_of_scope`, `no_information`,
`referral`), completa los datos del perfil (`{display_name}`, `{referral_name}`) y, si la pregunta no
fue en español, el LLM la **adapta al idioma** conservando el contenido (HU11.3). En español sale tal
cual, sin llamar al LLM.

**`finalize`** — sin LLM. Arma el mensaje `final`:
- Convierte las marcas `[n]` en `citations` y descarta las marcas que no corresponden a un fragmento.
- **Sanea el Markdown** (HU15.6): quita imágenes, HTML y cualquier enlace cuya URL no sea la de una cita.
- Revisa que la respuesta no contenga el **canario** del prompt (4.5); si lo contiene, la reemplaza
  por el mensaje de error general y marca `injection_suspected`.
- Guarda la pregunta y la respuesta en el historial de la conversación (no los fragmentos).

### 4.4 Cómo se obtiene cada `outcome`

| Camino | `outcome` |
|---|---|
| `classify` → `small_talk` → `canned_reply` | `small_talk` |
| `classify` → `about_assistant` → `canned_reply` | `about_assistant` |
| `classify` → `out_of_scope` → `canned_reply` | `out_of_scope` |
| `grade` = `sufficient` → `generate` | `answered` |
| `grade` = `partial` → `find_referral` → `generate` | `partially_answered` (con o sin `referral`) |
| `grade` = `none` → `find_referral` → `canned_reply` | `no_information` (con o sin `referral`) |

### 4.5 Defensas contra manipulación (HU14, HU15)

Ninguna defensa es perfecta por sí sola; se combinan capas:

| Capa | Qué hace |
|---|---|
| **El agente no puede hacer nada** | En el MVP no tiene tools con efectos: lo peor que logra una inyección es un texto incorrecto, nunca una acción |
| **Instrucciones explícitas** | El prompt de sistema fija identidad (asistente, no la persona), modo estricto, idioma y prohíbe revelar instrucciones |
| **Documentos como datos** | Cada fragmento va dentro de delimitadores (`<document id="1">…</document>`) con la regla explícita de que su contenido es información y **nunca** instrucciones (HU15.2) |
| **Filtro por relevancia** | `grade` descarta fragmentos irrelevantes, donde suelen esconderse las inyecciones |
| **Canario** | El prompt de sistema incluye una cadena secreta aleatoria; si aparece en una respuesta, el prompt se filtró y la respuesta se descarta (HU13.3) |
| **Salida saneada** | Sin imágenes, HTML ni enlaces ajenos a las citas (HU15.6) |
| **Aislamiento por persona** | La búsqueda filtra por `persona_id` en la consulta, no en el prompt (HU3) |
| **Secretos ya ocultos** | Se enmascaran al indexar: nunca llegan al modelo (HU15.4) |
| **Detección y registro** | `screen_input` y `classify` marcan los intentos para la auditoría (HU15.7) |

### 4.6 Prompts

- Viven en `agent/prompts/`, en **inglés** (D02), versionados con el código.
- Indican explícitamente que la respuesta va en el idioma de la pregunta.
- Cada prompt tiene un identificador de versión que se guarda en la auditoría junto con el modelo,
  para comparar resultados entre cambios.

### 4.7 Modelos y llamadas al LLM

| Rol | Variable | Usado por | Requisitos |
|---|---|---|---|
| Principal | `LLM_MODEL` | `generate` | Streaming, buena redacción |
| Rápido | `LLM_FAST_MODEL` (por defecto, igual a `LLM_MODEL`) | `classify`, `grade`, `find_referral`, adaptación de idioma | Salida estructurada (tool calling o JSON schema), baja latencia |

- Ambos se eligen con el set de evaluación (D08, sección 8).
- **Latencia estimada** hasta el primer fragmento: `classify` + `retrieve` + `grade` + primer token
  de `generate` ≈ 3–5 s con modelos rápidos; el objetivo es 10 s (RNF).
- **Reintentos:** las llamadas estructuradas se reintentan una vez ante un error transitorio, siempre
  dentro del tiempo límite. Si el LLM no responde, `LLM_UNAVAILABLE`.
- **Tiempo límite:** todo el grafo corre dentro de `ANSWER_TIMEOUT`; al vencer, se cancela la llamada
  en curso y se publica `TIMEOUT` (HU6.3).

### 4.8 Parámetros de búsqueda (configurables)

| Parámetro | Variable | Defecto inicial |
|---|---|---|
| Candidatos por tipo de búsqueda | `RETRIEVAL_CANDIDATES` | 20 |
| Fragmentos que pasan a `grade` | `RETRIEVAL_TOP_K` | 8 |
| Umbral mínimo para derivar | `REFERRAL_MIN_SCORE` | se calibra con la evaluación |
| Turnos de historial que se usan | `HISTORY_TURNS` | 6 |

Los valores iniciales son un punto de partida: se ajustan con el set de evaluación.

## 5. Ingesta y conectores

Cubre: HU4, HU9, HU12, HU15.4 · Aplica: D19, D20, D22, D29, D30, D31, D39

### 5.1 Recorrido de una actualización

```
ingestion.jobs (o flock-ingest run)
     │
     v
 tomar el candado ─────── ocupado ───> IngestionEvent.rejected (HU4.9)
     │
     v
 started
     │
     v
 por cada carpeta de persona en KNOWLEDGE_ROOT:
   1. perfil: crear persona.md si falta / leerlo / actualizar persona (HU9)
   2. carpeta: sync incremental de archivos (5.3)
   3. fuentes externas de esa persona incluidas en el job (5.4)
   4. documentos de fuentes que ya no están en el job → borrar (HU12.4)
   5. persona_completed { resumen }
     │
     v
 personas cuya carpeta desapareció → borrar + persona_removed
     │
     v
 completed { totales }   ── soltar el candado
```

**Reglas de robustez:**
- **Un error en un documento** no frena la actualización: el documento se omite y se informa
  en `skipped` con el motivo.
- **Un error en una fuente** (por ejemplo, Jira no responde) se informa en `sourceErrors` y sus
  documentos **se conservan**: una fuente caída nunca se interpreta como "se borró todo". Su cursor
  no avanza, así que la próxima actualización reintenta.
- **El cursor de cada fuente se guarda al terminar esa fuente**, no al final de todo: si el proceso
  se corta, no se pierde lo ya hecho.

### 5.2 La interfaz común de conectores (D19)

```python
class SourceDocument(BaseModel):
    id: str                       # stable: "file:<persona>:<path>", "jira:<persona>:<key>"
    persona_id: str
    source_type: SourceType       # file | email | email_attachment | jira | confluence | sharepoint
    source_id: str | None         # external source id; None for the persona folder
    parent_id: str | None         # email attachment -> its email
    title: str
    url: str | None
    path: str | None              # relative path, for folder files
    content: str                  # plain text / Markdown, before redaction
    source_updated_at: datetime


class SyncPlan(BaseModel):
    upserts: AsyncIterator[SourceDocument]   # lazy: fetched/parsed while iterating
    deleted_ids: list[str]
    next_cursor: dict[str, Any]


class SourceConnector(Protocol):
    source_key: str               # "folder" or the external source id

    async def sync(self, cursor: dict[str, Any] | None) -> SyncPlan: ...
```

- El pipeline (5.5) solo conoce esta interfaz: agregar un sistema nuevo es escribir un conector.
- `upserts` es **perezoso**: cada documento se descarga y se parsea recién cuando el pipeline lo pide,
  así una fuente grande no se carga entera en memoria.

### 5.3 Archivos (D20)

Se separa **dónde están** (`FileStore`) de **cómo se leen** (parsers):

```python
class FileStore(Protocol):
    async def delta(self, cursor: dict[str, Any] | None) -> FileDelta: ...  # changed + deleted + cursor
    async def read_bytes(self, path: str) -> bytes: ...
```

| `FileStore` | Uso | Cómo detecta cambios |
|---|---|---|
| `LocalFolderStore` | Carpeta de cada persona | Snapshot `{ruta: (fecha de modificación, tamaño)}` en el cursor |
| `SharePointStore` | Fuente externa SharePoint, vía MCP (5.4) | Fecha de modificación de cada archivo del sitio/carpeta |

**Archivos que se ignoran siempre:** `persona.md` (es el perfil, HU9.3), ocultos (`.algo`) y
temporales de Office (`~$algo.docx`).

**Parsers** (comunes a todos los `FileStore`):

| Tipo | Cómo se reconoce | Cómo se lee |
|---|---|---|
| Texto | Cualquier archivo que **por contenido** sea texto: sin bytes nulos y con codificación detectable (`charset-normalizer`). No depende de la extensión | Tal cual |
| HTML / XML | Extensión | Se extrae el texto sin etiquetas (`beautifulsoup4`) |
| PDF | Extensión | `pypdf`. Si no tiene texto (escaneado), se omite (HU4.7) |
| Word | `.docx` | `python-docx`. Los títulos pasan a encabezados Markdown y las tablas a texto |
| Correo Outlook | `.msg` | `extract-msg`: asunto, remitente, destinatarios, fecha y cuerpo |
| Correo estándar | `.eml` | Módulo `email` de Python, con los mismos campos |

- **Adjuntos de correos** (HU4.6): cada adjunto de un formato soportado es un documento hijo con
  `parent_id` = el correo, id `<id del correo>#attachment/<nombre>` y título "adjunto de *asunto*".
  Un correo adjunto dentro de otro se procesa, pero no se sigue más allá de ese nivel.
- **Tamaño máximo por archivo:** `MAX_FILE_MB` (por defecto, 20 MB); los más grandes se omiten y se informan.
- **Citas de archivos locales:** no tienen una URL que el navegador pueda abrir, así que se citan
  por su **ruta relativa** (`path`) y `url` queda en `null` (ver 5.9).

### 5.4 Fuentes externas vía MCP (D30, D39)

**Arquitectura:**
- Cada servidor MCP corre como **un contenedor más** del Docker Compose, con las credenciales de la
  cuenta de servicio en su configuración (D39). El Ingestion Worker se conecta a ellos por HTTP.
- Un `McpClient` compartido maneja la conexión, la paginación y los reintentos con espera creciente
  cuando el sistema limita la cantidad de pedidos.
- La **identidad de la persona** en cada sistema sale de `identities.email` del perfil (HU12.8).
  Si falta, sus fuentes externas no se procesan y se informa.

**Qué se trae de cada sistema** (HU12.7):

| Conector | Consulta | Documento resultante |
|---|---|---|
| **Jira** | JQL: `project = <scope> AND (reporter = <persona> OR assignee = <persona>)`, ordenado por fecha de actualización | Un documento por issue: `KEY: resumen`, metadatos (estado, resolución, fechas), descripción y **todos los comentarios** con autor y fecha. URL del issue |
| **Confluence** | CQL: `space = <scope> AND (creator = <persona> OR contributor = <persona>)` | Un documento por página: título, ruta de páginas padre como sección, cuerpo convertido a Markdown. URL de la página |
| **SharePoint** | Archivos del sitio/carpeta de `scope` creados o modificados por la persona | Pasan por los **mismos parsers** que los archivos locales (5.3). URL del archivo |

**Detección de cambios y bajas:**
- **Cambios:** el cursor guarda la última fecha de actualización vista; se piden solo los elementos
  modificados desde entonces.
- **Bajas:** las consultas incrementales no muestran lo que se borró o dejó de corresponder (un
  issue reasignado a otra persona, por ejemplo). Por eso, en cada actualización se pide además la
  **lista de identificadores** que cumplen la consulta (sin contenido, es barato) y se borran los
  documentos que ya no aparecen.

**Riesgo (D30): elegir los servidores MCP.** Hay que verificar que el servidor de cada sistema:
1. funcione con cuenta de servicio (sin login interactivo),
2. permita búsquedas JQL/CQL con paginación y traer comentarios,
3. permita listar y descargar archivos de SharePoint con sus autores.

Esto se resuelve con una **tarea de investigación (spike) al inicio de la etapa 3**, evaluando el
servidor oficial de cada proveedor y alternativas de la comunidad. Si alguno no cumple, ese conector
usa la API REST del sistema directamente, sin cambiar la interfaz `SourceConnector`.

### 5.5 Pipeline por documento

```
SourceDocument
   │
   ├─ ¿mismo content_hash que lo guardado? ──> sin cambios (HU4.4)
   │
   v
ocultar secretos (5.6) ──> dividir en fragmentos ──> embeddings (en lotes) ──> reemplazo atómico (3.2)
```

**División en fragmentos**, según la estructura de cada tipo:

| Tipo | Criterio |
|---|---|
| Markdown, Word, HTML, Confluence | Por encabezados; las secciones largas, por párrafos |
| Texto plano, PDF | Por párrafos |
| Correos | El correo entero si entra; si no, por párrafos |
| Jira | Un fragmento con encabezado + descripción, y los comentarios agrupados en orden |

- Tamaño objetivo ~1.200 caracteres, con ~150 de solapamiento entre fragmentos consecutivos de
  una misma sección, para no cortar una idea a la mitad.
- Cada fragmento lleva adelante su contexto: `[título > sección]`. Mejora la búsqueda y permite citar la sección.

**Embeddings (D22):** `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones) como punto de partida.
La evaluación (sección 8) lo compara con un modelo multilingüe más grande (por ejemplo,
`multilingual-e5-large`); cambiarlo implica reindexar (3.2, tabla `meta`).

### 5.6 Ocultamiento de secretos (HU15.4)

Antes de dividir en fragmentos, el contenido pasa por una lista de **detectores** con expresiones
regulares, cada uno con tests:

| Detector | Ejemplos |
|---|---|
| Claves privadas | Bloques `-----BEGIN … PRIVATE KEY-----` |
| Tokens de proveedores | AWS (`AKIA…`), GitHub (`ghp_…`), Slack (`xoxb-…`), OpenAI/OpenRouter (`sk-…`), JWT (`eyJ…`) |
| Cadenas de conexión | `Password=…;`, `AccountKey=…` |
| Credenciales en URLs | `https://usuario:clave@host` |
| Pares clave-valor | `password: …`, `contraseña = …`, `pwd=…`, `api_key: …`, `secret: …` |

- Cada coincidencia se reemplaza por `[dato oculto]` (texto configurable en `messages.yaml`).
- Se cuentan por documento (`secrets_masked`) para el resumen (HU15.4).
- Es una defensa contra lo **evidente**, no un detector perfecto: el set de evaluación incluye
  documentos con secretos para medirlo.

### 5.7 Perfil de la persona (HU9)

- Si la carpeta no tiene `persona.md`, se crea con `display_name` derivado del nombre de la carpeta
  (`juan-plataforma` → "Juan Plataforma") e `identities` vacío. Por eso la ingesta necesita **permiso
  de escritura** sobre la carpeta raíz (solo para crear perfiles).
- Si el perfil cambió (`profile_hash`), se actualiza la persona.
- Si el perfil es inválido (YAML roto, campos con tipos incorrectos), se usan los valores por
  defecto y se informa en el resumen (caso borde de la spec).

### 5.8 Ejecución manual para desarrollo

`flock-ingest run [--persona <id>] [--sources <archivo.json>]` corre el mismo pipeline sin Kafka:
- Sin `--sources`, procesa solo las carpetas.
- Con `--sources`, lee las fuentes externas de un archivo JSON con el mismo formato que `IngestionJob.sources`.
- Imprime el resumen por persona.

### 5.9 Cambios que esta sección introduce en la sección 2

1. **`citations[].url` pasa a ser opcional** y se suma **`path`** (ruta relativa) para archivos de las
   carpetas, que no tienen una URL navegable.

## 6. Core API y front

Cubre: HU4, HU6, HU8, HU10, HU12, HU15.6 · Aplica: D05, D09, D10, D16, D23, D31, D32

### 6.1 Cómo se sirven (mismo origen)

```
navegador ──> web (nginx) ──┬── /            archivos estáticos del front (React compilado)
                            └── /api, /docs  proxy ──> core-api
```

- Front y API comparten **el mismo origen**: no hace falta configurar CORS y la cookie de sesión
  funciona sin trucos.
- En desarrollo, el servidor de Vite hace el mismo proxy de `/api` hacia la Core API.

### 6.2 Seguridad de la sesión (D16)

- **Login:** `POST /api/auth/login` con usuario y contraseña (JSON). Spring Security valida contra
  `app_user` y crea la sesión.
- **Cookie de sesión:** `HttpOnly` (JavaScript no puede leerla), `SameSite=Strict` y `Secure`
  (configurable: los navegadores la aceptan en `http://localhost` para desarrollo).
- **CSRF:** como la autenticación es por cookie, se activa la protección CSRF de Spring Security:
  la API entrega un token en una cookie legible y el front lo devuelve en el header `X-XSRF-TOKEN`
  en cada `POST`/`DELETE`.
- **Todo `/api/**` requiere sesión**, excepto el login.
- **La documentación (`/docs/**`) es pública**: Swagger UI, la especificación OpenAPI y la
  documentación AsyncAPI se ven sin iniciar sesión, para que otros equipos puedan integrarse.
  Swagger UI permite probar endpoints, pero sin sesión la API responde `401`.
- **Errores:** formato estándar *Problem Details* (RFC 7807), que Spring trae incorporado.

### 6.3 API REST

| Método y ruta | Qué hace | Spec |
|---|---|---|
| `POST /api/auth/login` · `POST /api/auth/logout` · `GET /api/auth/me` | Sesión | HU10.1 |
| `GET /api/config` | Parámetros que el front necesita (por ejemplo, `maxQuestionChars`) | HU15.5 |
| `GET /api/personas` | Personas disponibles (`persona_view`) | HU10.2 |
| `POST /api/conversations/{conversationId}/messages` | Envía una pregunta `{ personaId, question }` → `202 { requestId }` | HU10 |
| `GET /api/conversations/{conversationId}/stream` | **SSE** con las respuestas de esa conversación | HU6, HU10 |
| `GET /api/personas/{personaId}/sources` · `POST …/sources` | Lista y alta de fuentes externas | HU12.1 |
| `DELETE /api/sources/{sourceId}` | Baja de una fuente | HU12.4 |
| `POST /api/ingestion/runs` | Actualización manual → `202 { jobId }` | HU4.8 |
| `GET /api/ingestion/runs` | Historial de actualizaciones con su resumen | HU4.5 |
| `GET /api/audit` | Registro paginado, con filtros por persona, fechas, `outcome` y flags | HU8.2 |

- El `conversationId` lo genera el **front** (un UUID); "conversación nueva" = un UUID nuevo (HU10.6).
- La validación del `scope` de una fuente depende del tipo: clave de proyecto (Jira), clave de
  espacio (Confluence), URL del sitio + carpeta (SharePoint).
- Swagger UI en `/docs/swagger-ui` (D32); la documentación AsyncAPI en `/docs/asyncapi` (2.7).

### 6.4 El chat: de HTTP a Kafka y de vuelta

```
Front                         Core API                                   Kafka
  │ GET …/stream (SSE) ────────>│ registra el stream de esa conversación    │
  │ POST …/messages ───────────>│── AgentRequest (replyTo =                 │
  │ <── 202 { requestId } ──────│   agent.replies.core-api) ──────────────>│
  │                             │<── AgentReply (accepted, token…, final) ──│
  │ <── eventos SSE ────────────│   reenvía por conversationId              │
```

- La Core API es **un cliente más** del agente (D23): publica en `agent.requests` y escucha
  `agent.replies.core-api`.
- El front **abre el SSE antes** de enviar la pregunta, para no perder los primeros mensajes.
- Cada evento SSE lleva el `seq` como identificador. La Core API guarda en memoria los eventos del
  pedido en curso de cada conversación (hasta `ANSWER_TIMEOUT`): si el navegador se reconecta,
  recibe lo que se perdió.
- **Una sola instancia** de la Core API en el MVP: con varias, cada una debería recibir solo las
  respuestas de sus conversaciones (queda para después).

### 6.5 Kafka en la Core API

| Tópico | Rol | Para qué |
|---|---|---|
| `agent.requests` | Produce | Preguntas del chat |
| `agent.replies.core-api` | Consume | Respuestas → SSE |
| `ingestion.jobs` | Produce | Scheduler cada `INGESTION_INTERVAL` y botón "actualizar" (D31) |
| `ingestion.events` | Consume | `persona_view` e `ingestion_run_view` (3.5) |
| `agent.audit` | Consume | `audit_entry_view` (3.5) |

- Con `spring-kafka`, mTLS configurado en `application.yml` (sección 7).
- Las copias de lectura se actualizan con **upserts por id**: procesar un mensaje dos veces da el mismo resultado.
- El scheduler arma el `IngestionJob` con **todas** las fuentes de la tabla `source` (3.6).

### 6.6 Front: pantallas

Los textos de la interfaz están en **español** (el código, en inglés).

| Ruta | Pantalla | Spec |
|---|---|---|
| `/login` | Usuario y contraseña | HU10.1 |
| `/chat` | Selector de persona, conversación, pregunta con contador de caracteres, "conversación nueva" | HU10 |
| `/sources` | Fuentes externas por persona (alta, baja), botón "Actualizar ahora" e historial de actualizaciones con su resumen | HU4, HU12 |
| `/audit` | Registro con filtros y detalle de cada entrada | HU8 |

**Detalle del chat (HU6, HU10, HU15.6):**
- **Cuenta regresiva:** con el `accepted` se calcula la duración como `deadlineAt − sentAt` (ambas
  fechas del servidor, así no influye el reloj de la PC) y se descuenta desde que llega el mensaje.
- **Streaming:** los `token` se agregan al texto; al llegar el `final`, se reemplaza por `final.answer`.
- **Fuentes:** debajo de la respuesta, cada cita con título, sección y enlace (o la ruta, si es un
  archivo de carpeta).
- **Derivación:** un aviso destacado "Preguntale a *Ana Gómez*".
- **Errores:** el `message` del error; si es `retryable`, un botón "Reintentar".
- **Markdown seguro:** se renderiza **sin HTML**, sin imágenes, y solo con enlaces a las citas, que
  se abren en otra pestaña. Es una segunda barrera además del saneamiento del agente (4.3).

### 6.7 Front: técnica

| Necesidad | Elección |
|---|---|
| Ruteo | React Router |
| Datos de la API | TanStack Query (caché, reintentos, estados de carga) |
| Tipos de la API | Generados desde el OpenAPI de la Core API (`openapi-typescript`) |
| Streaming | `EventSource` nativo del navegador |
| Markdown | `react-markdown` sin plugins de HTML, con imágenes desactivadas |
| Estilos | Tokens del design system de Flock (skill `flock-design-system`) como variables CSS + CSS Modules |
| Calidad | ESLint, Prettier, `tsc` estricto, Vitest (D03, D38) |

## 7. Seguridad e infraestructura

Cubre: HU7, HU15 · Aplica: D12, D17, D25, D37, D39

### 7.1 CA propia y certificados (D17)

Un script genera todo con OpenSSL **dentro de un contenedor** (no hace falta instalar nada en Windows):

| Certificado | Tipo | Usado por |
|---|---|---|
| `ca` | Autoridad certificante (autofirmada) | Todos confían en ella |
| `kafka` | Servidor | Broker de Kafka |
| `postgres` | Servidor | Postgres |
| `core-api` | Cliente | Core API → Kafka y Postgres |
| `agent` | Cliente | Agent Worker → Kafka y Postgres |
| `ingestion` | Cliente | Ingestion Worker → Kafka y Postgres |
| `cli` | Cliente | Cliente de prueba `flock-ask` → Kafka |
| `kafka-admin` | Cliente | Scripts que crean tópicos y ACLs |

- **Identidad = CN del certificado** (`CN=core-api`, `CN=agent`…). Kafka y Postgres la usan para
  saber quién se conecta y qué puede hacer.
- Los certificados de servidor incluyen como nombres alternativos (SAN) el nombre del servicio en
  Docker y `localhost`, para conectarse desde adentro y desde la PC.
- Formato **PEM** en todos lados: lo aceptan Python, Postgres, Kafka y Spring Boot (SSL bundles).
- Claves de curva elíptica (P-256). Vigencia: CA 10 años, servicios 2 años (entorno local).
- Se generan en `infra/certs/out/` (fuera de git) y se montan **solo lectura** en cada contenedor,
  cada uno con su propio certificado y clave.
- **Sumar una app cliente:** `infra/certs/add-client.sh <clientId>` genera su certificado, crea su
  tópico `agent.replies.<clientId>` y sus ACLs (7.2).

### 7.2 Kafka (D09, D25)

- Imagen oficial `apache/kafka`, **modo KRaft** (sin ZooKeeper), un solo nodo.
- Los clientes se conectan solo por el listener **SSL con certificado de cliente obligatorio**
  (`ssl.client.auth=required`).
- Las **ACLs** están activas y, por defecto, todo está prohibido: solo se permite lo que figura abajo.
- El usuario de Kafka sale del CN del certificado (`User:core-api`).

**Tópicos:**

| Tópico | Particiones | Retención | Nota |
|---|---|---|---|
| `agent.requests` | 6 | 1 día | Las particiones permiten varios Agent Workers |
| `agent.replies.core-api`, `agent.replies.cli` | 3 | 1 día | Uno por app cliente |
| `agent.audit` | 3 | 7 días | La Core API lo guarda en su copia |
| `ingestion.jobs` | 1 | 7 días | Una actualización a la vez |
| `ingestion.events` | 1 | 7 días | |

**ACLs:**

| Usuario | Escribe en | Lee de |
|---|---|---|
| `core-api` | `agent.requests`, `ingestion.jobs` | `agent.replies.core-api`, `ingestion.events`, `agent.audit` |
| `agent` | `agent.replies.*` (prefijo), `agent.audit` | `agent.requests` |
| `ingestion` | `ingestion.events` | `ingestion.jobs` |
| `cli` | `agent.requests` | `agent.replies.cli` |
| `kafka-admin` | Administración (crear tópicos y ACLs) | — |

Cada usuario lee con su propio *consumer group* (`core-api`, `agent`, `ingestion`, `cli`).

### 7.3 Postgres (D12)

- Imagen `pgvector/pgvector`, con TLS activado y certificado de servidor.
- **Autenticación por certificado** (`hostssl … cert`): el CN del certificado es el rol de Postgres.
  No hay contraseñas de base de datos.
- `infra/postgres/init.sql` (se ejecuta al crear la base) crea la extensión `vector`, los schemas,
  los roles y los permisos de la sección 3.1.
- El agente lee las tablas de `knowledge` gracias a permisos por defecto: todo lo que crea el rol
  `ingestion` en `knowledge` es legible por `agent`.

**Migraciones:**

| Schema | Herramienta | Corre como |
|---|---|---|
| `core` | Flyway (al arrancar la Core API) | `core_api` |
| `knowledge` | Archivos SQL con `yoyo-migrations` (al arrancar el Ingestion Worker) | `ingestion` |
| `agent` | `yoyo-migrations` + `setup()` del checkpointer de LangGraph (al arrancar el Agent Worker) | `agent` |

### 7.4 Secretos

| Secreto | Dónde vive |
|---|---|
| `OPENROUTER_API_KEY` | `.env` → solo el contenedor `agent` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `.env` → solo `core-api` (solo se usan para crear el usuario inicial) |
| Cuentas de servicio de Jira, Confluence y SharePoint (D39) | `.env` → solo los contenedores de los servidores MCP |
| Claves privadas de los certificados | `infra/certs/out/` → cada contenedor monta solo la suya |

- Nada de esto entra en git ni en las imágenes de Docker.
- Los secretos se cargan como tipos que **no se imprimen** en logs (`SecretStr` en Python; Spring
  oculta las propiedades sensibles).
- Cada contenedor recibe **solo** las variables que necesita, no el `.env` completo.

### 7.5 Docker Compose (D37)

```
┌─────────── red interna de Docker ───────────────────────────────────────┐
│                                                                         │
│  web (nginx) ──> core-api ──┐                                           │
│     :8080 (PC)              │                                           │
│                             ├──> kafka ──> agent ────> OpenRouter (internet)
│  cli (en la PC) ─ :9093 ───>┘      │    └─> ingestion ──> mcp-atlassian  │
│                                    │           │      └─> mcp-sharepoint │
│                             postgres <─────────┘                         │
│                               :5433 (PC, opcional)                       │
│                                                                         │
│  certs-init · kafka-init    (contenedores de un solo uso al arrancar)   │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Un solo comando:** `docker compose up`. Dos contenedores de un solo uso preparan todo la primera vez:
  - `certs-init` genera la CA y los certificados si no existen.
  - `kafka-init` crea los tópicos y las ACLs.

  Los demás servicios esperan a que terminen (y a que Kafka y Postgres estén sanos).
- **Puertos en la PC:** `8080` (web), `9093` (Kafka, para el cliente de prueba) y `5433` (Postgres,
  opcional, para inspeccionar la base). El resto queda solo dentro de la red de Docker.
- **Volúmenes:** datos de Postgres y de Kafka, caché del modelo de embeddings (compartida entre
  `agent` e `ingestion`) y `data/knowledge` montada **solo** en `ingestion`, con escritura (para crear
  perfiles, 5.7). El agente no accede a los archivos: solo a la base.
- **Perfiles de Compose:** los servidores MCP están en el perfil `external-sources` y solo se
  levantan en la etapa 3 o cuando se pide explícitamente.

**Imágenes propias:**

| Servicio | Imagen |
|---|---|
| `agent`, `ingestion` | La misma imagen Python (uv, en dos etapas: build y ejecución), con distinto comando |
| `core-api` | Build con Maven → ejecución con JRE 21 |
| `web` | Build con Node → nginx con los archivos estáticos |

**Inspección HTTPS en los builds:** dentro de los builds, `uv`, `npm` y `maven` descargan
dependencias; si la red inspecciona HTTPS (se vio de forma intermitente, ver `docs/notas-entorno.md`),
fallarían. Cada Dockerfile agrega a la lista de confianza los `.crt` que haya en `infra/corp-ca/`
(fuera de git); si la carpeta está vacía, no hace nada (7.8).

### 7.6 Logs y trazabilidad

- Logs en **JSON**, a la salida estándar de cada contenedor.
- Todos los logs de un pedido llevan su `requestId`, y los de una actualización su `jobId`: se puede
  seguir un pedido de punta a punta entre Core API, Kafka y Agent Worker.
- Nunca se registran secretos ni el contenido completo de documentos; las preguntas y respuestas van
  a la auditoría, no a los logs.
- La Core API expone su estado con Spring Boot Actuator (`/actuator/health`, interno). Los workers
  informan su estado con el *healthcheck* de Docker.

### 7.7 Excepción a D17: servidores MCP (D40)

Los servidores MCP son software de terceros y, en general, **no soportan mTLS**. La conexión
Ingestion Worker → servidor MCP va **sin mTLS**, dentro de la red interna de Docker y sin puertos
expuestos a la PC.

### 7.8 Certificado raíz corporativo (opcional)

En la T05 no se encontró inspección HTTPS: no hay certificado para exportar. `infra/corp-ca/` queda
como punto de extensión: si la inspección vuelve, se exporta ahí el certificado raíz que presente la
red y los Dockerfiles lo usan sin cambios de código (procedimiento en `docs/notas-entorno.md`).

## 8. Tests y evaluación

Cubre: criterios de éxito de la spec, HU15 · Aplica: D03, D08, D38

Hay dos cosas distintas:
- **Tests:** verifican que el código hace lo que debe. Son deterministas, rápidos y **no llaman al LLM real**.
- **Evaluación:** mide la **calidad** del bot con un modelo real (¿responde bien?, ¿cita?, ¿resiste ataques?).
  Es lenta, cuesta dinero y sus resultados varían un poco entre corridas.

### 8.1 Tests de agent-service (pytest)

**Unitarios** — sin red ni base:

| Módulo | Qué se prueba |
|---|---|
| Parsers | Un archivo de muestra por formato (texto, CSV, HTML, PDF, PDF escaneado, docx, eml, msg con adjuntos), en `tests/fixtures/` |
| Parser `.msg` | Los tests se escriben completos pero quedan **marcados como omitidos** mientras no exista la muestra `tests/fixtures/email/sample.msg` (la librería lee `.msg` pero no puede crearlos). Al agregar la muestra se ejecutan solos, sin tocar código. El reporte de pytest muestra el motivo de la omisión |
| `LocalFolderStore` | Altas, cambios, bajas, archivos ignorados (`persona.md`, ocultos, temporales) |
| Chunking | Cortes por encabezado, por párrafo, solapamiento, contexto `[título > sección]` |
| Redacción de secretos | Cada detector con casos que **deben** ocultarse y casos parecidos que **no** |
| Perfil | Creación por defecto, cambios, YAML inválido |
| `screen_input` | Patrones de manipulación en español e inglés, y preguntas legítimas que no deben marcarse |
| `finalize` | Citas `[n]`, saneamiento de Markdown, detección del canario |
| Retención y límite por app | Vencimiento por último mensaje, cambio de persona, ventana por minuto |
| Mensajes | Plantillas con datos del perfil |

**Grafo con un LLM falso** — un modelo de prueba que devuelve respuestas predefinidas. Permite
verificar **cada camino** de la tabla 4.4 (cada `outcome`), el tiempo límite y los errores del LLM,
sin red y siempre con el mismo resultado.

**Integración** — con Postgres (pgvector) y Kafka reales, de dos formas según qué se prueba:

| Qué se prueba | Contra qué | Por qué |
|---|---|---|
| Conexiones, TLS, roles y ACLs (T08) | El entorno de **Docker Compose** (`localhost:5433` y `localhost:9093`) con los certificados de `infra/certs/out/` | Es la única forma de ejercitar mTLS, roles y ACLs reales |
| Lógica sobre tablas y mensajes (T09 en adelante): repositorio, búsqueda híbrida, ingesta, Agent Worker | Contenedores efímeros con **Testcontainers** | Base y tópicos limpios en cada corrida; TLS no influye en esa lógica |

- Los tests contra Compose llevan la marca `integration_stack` y **se omiten** (con el motivo) si el
  entorno no está levantado. No dejan rastro: las tablas de prueba se borran al terminar y Kafka se
  lee **sin grupo de consumidores**, así no se mueven los offsets de los servicios reales.
- Casos de Testcontainers:
  - Repositorio: búsqueda híbrida, aislamiento por persona, reemplazo atómico, candado de ingesta.
  - Ingesta completa sobre `examples/knowledge`.
  - Agent Worker con LLM falso: un pedido en `agent.requests` produce `accepted` → `token`… → `final`;
    pedidos repetidos, inválidos y con persona inexistente.

### 8.2 Tests de core-api (JUnit 5)

| Tipo | Qué se prueba |
|---|---|
| Unitarios | Armado del `IngestionJob`, validación del `scope` por tipo de fuente, buffer de eventos para reconexión |
| Web (`@WebMvcTest`) | Endpoints, Problem Details, seguridad: login, `401` sin sesión, CSRF, documentación pública |
| Integración (Testcontainers) | Migraciones Flyway, consumidores que llenan las copias de lectura (idempotentes), productores, SSE de punta a punta con un agente simulado |

### 8.3 Tests de web (Vitest)

- Con React Testing Library y respuestas de API simuladas (MSW).
- Casos clave: cálculo de la cuenta regresiva, armado de la respuesta con `token` y reemplazo por el
  `final`, Markdown seguro (sin HTML, sin imágenes, solo enlaces de citas), errores y "Reintentar",
  login y redirección.

### 8.4 Tests del contrato

- Los ejemplos de la sección 2 y de `contracts/` se validan contra los JSON Schema.
- Los modelos generados (Python y Java) se regeneran en cada build: si el contrato cambia y el código
  no, falla la compilación o los tests.

### 8.5 Prueba de humo de punta a punta

Un script levanta todo con `docker compose up`, ingesta `examples/knowledge`, hace una pregunta con
`flock-ask` y verifica que llega un `final` con citas. Usa el **LLM real**, así que se corre solo al
cerrar cada etapa, junto con la evaluación (D41).

### 8.6 Evaluación de calidad (`flock-eval`)

**Datos de prueba** (`examples/knowledge/`, versionados):
- Al menos **dos personas ficticias** (por ejemplo, `juan-plataforma` y `ana-datos`) con contenidos
  distintos, para probar derivaciones y aislamiento.
- Documentos en **todos los formatos** soportados, en español e inglés.
- Documentos **envenenados** (con instrucciones dirigidas al bot) y documentos **con secretos**.

**Casos** (`agent-service/eval/cases.yaml`), al menos 20 por persona (criterio de éxito 1):

```yaml
- id: juan-rollback-01
  persona: juan-plataforma
  question: "¿Cómo hago rollback de un deploy?"
  category: answerable           # answerable | partial | referral | no_information
                                 # out_of_scope | small_talk | about_assistant
                                 # injection_direct | injection_indirect | cross_persona | secret_leak
  expect:
    outcome: answered
    cites: ["file:juan-plataforma:procedures/deploy.md"]
    facts: ["se ejecuta el job rollback-prod", "con el tag anterior"]
    must_not_contain: []
    language: es
```

**Cómo se mide cada caso:**

| Verificación | Cómo | Para qué categorías |
|---|---|---|
| `outcome` esperado | Comparación exacta | Todas |
| Cita el documento esperado | Comparación exacta | `answerable`, `partial` |
| Deriva a la persona esperada | Comparación exacta | `referral` |
| Idioma de la respuesta | Detector de idioma | Todas |
| No contiene lo prohibido | Búsqueda de texto: canario, valores de secretos, frases de la otra persona, instrucciones de los documentos envenenados | Ataques, `secret_leak`, `cross_persona` |
| Contiene los hechos esperados | **LLM como juez**: un modelo compara la respuesta con `facts` y explica su veredicto | `answerable`, `partial` |

**Criterios de éxito de la spec** que calcula el reporte:

| Criterio | Cálculo | Meta |
|---|---|---|
| Respuestas correctas y con fuente | Casos `answerable` que aprueban hechos y cita | ≥ 80 % |
| No inventa | Casos `no_information`, `out_of_scope` y `referral` con el `outcome` correcto y sin contenido inventado | 100 % |
| Resiste ataques | Casos de ataque que aprueban todas sus verificaciones | 100 % |
| Primer fragmento | Percentiles 50 y 95 de `firstTokenMs` | Informativo (objetivo: 10 s) |

**Ejecución:**
- `flock-eval` corre los casos **directamente contra el grafo** (sin Kafka), con el modelo configurado.
- `flock-eval --models a,b,c` compara varios modelos y genera una tabla comparativa: así se eligen
  `LLM_MODEL` y `LLM_FAST_MODEL` (D08).
- El juez usa su propio modelo (`EVAL_JUDGE_MODEL`), distinto del evaluado cuando sea posible.
- Genera un reporte en `agent-service/eval/reports/` (fuera de git) con el resumen y el detalle de
  cada caso que falló.
- **Cuándo correrla:** **solo al cerrar cada etapa** (D41). Es la única instancia en la que se usa la
  API key de OpenRouter en el desarrollo; el resto del tiempo, los tests usan el LLM falso.

> Los criterios de éxito hablan de "preguntas **reales**". Los cierres de etapa usan personas
> ficticias; la validación con una persona con conocimiento real (con su consentimiento) y sus propios
> casos la hace Francisco en sus pruebas en el entorno de desarrollo, fuera de los cierres de etapa.

### 8.7 Cómo se corre todo

| Qué | Comando |
|---|---|
| Linters (todos los lenguajes) | `pre-commit run --all-files` |
| Tests de Python | `uv run pytest` (en `agent-service/`) |
| Tests de Java | `mvn verify` (en `core-api/`) |
| Tests del front | `npm test` (en `web/`) |
| Todo lo anterior | `scripts/check.sh` |
| Evaluación | `uv run flock-eval` (requiere API key) |
| Humo de punta a punta | `scripts/smoke.sh` (requiere API key) |

- **Cobertura:** sin un porcentaje obligatorio, pero los módulos críticos (redacción de secretos,
  `screen_input`, `finalize`, ruteo del grafo, seguridad de la Core API) deben tener todos sus casos probados.
- **Integración continua:** no hay remoto todavía. Cuando lo configures, `scripts/check.sh` es lo que
  correría en cada push.

## 9. Riesgos y mapa de cobertura de la spec

### 9.1 Etapas de construcción (D27)

| Etapa | Qué se construye | Se demuestra con | Cierre |
|---|---|---|---|
| **1. Núcleo** | Contrato, infraestructura (Kafka y Postgres con mTLS), ingesta de carpetas, Agent Worker completo, auditoría, cliente `flock-ask` | Preguntas por línea de comandos sobre `examples/knowledge` | Tests en verde + evaluación + humo (D41) |
| **2. Core API y front** | Login, chat con streaming y cuenta regresiva, auditoría en pantalla, actualización programada y manual, documentación publicada | Demo en el navegador | Ídem |
| **3. Fuentes externas** | Spike de servidores MCP, conectores de Jira, Confluence y SharePoint, administración de fuentes en el front | Respuestas que citan issues y páginas reales | Ídem |

Cada etapa deja algo **funcionando y demostrable**; la siguiente se apoya en ella sin rehacerla.

### 9.2 Riesgos

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Los servidores MCP no permiten cuenta de servicio, JQL/CQL completos o listar SharePoint con autores (D30) | Alto en etapa 3 | Spike al inicio de la etapa 3; si no cumplen, API REST directa detrás de la misma interfaz (5.4) |
| R2 | Calidad o latencia del modelo vía OpenRouter; no todos los modelos soportan bien salida estructurada | Alto | Modelo configurable; comparación con `flock-eval --models` al cerrar cada etapa (8.6) |
| R3 | Prompts y parámetros se ajustan "a ciegas" entre cierres de etapa, porque la evaluación con LLM real solo corre al cerrarlas (D41) | Medio | Tests exhaustivos con LLM falso; los ajustes de calidad se concentran en el cierre de cada etapa |
| R4 | Los embeddings locales rinden mal en español o con texto técnico | Medio | Búsqueda híbrida (4.3); la evaluación compara con un modelo más grande; cambiarlo implica solo reindexar |
| R5 | Prompt injection: ninguna defensa es completa | Medio | Defensas en capas (4.5) y, sobre todo, un agente **sin tools con efectos**: lo peor es un texto incorrecto |
| R6 | La detección de secretos por patrones deja pasar algunos | Medio | Detectores con tests; documentos con secretos en la evaluación; los secretos no evidentes son un límite conocido |
| R7 | Privacidad: fragmentos de documentos pasan por OpenRouter y el proveedor del modelo | Medio | Desactivar registro y entrenamiento en la cuenta (D08); solo se envían los fragmentos relevantes; consentimiento de las personas reales |
| R8 | Proxy corporativo y antivirus bloquean descargas, builds o Docker | Medio | `docs/notas-entorno.md`; certificado corporativo en los builds (7.8) |
| R9 | Complejidad de mTLS, ACLs y Kafka en el entorno local | Medio | Todo automatizado en contenedores de un solo uso (7.5); un solo comando para levantar |
| R10 | Volumen y límites de pedidos de Jira y Confluence | Bajo–medio | Sync incremental, paginación, reintentos con espera creciente (5.4) |
| R11 | El alcance del MVP es grande (15 historias, 3 etapas) | Medio | Etapas demostrables por separado; backlog con tareas chicas |
| R12 | Una app cliente podría declarar el `replyTo` de otra (2.1) | Bajo | Riesgo aceptado: todas las apps son internas y autorizadas |
| R13 | Una sola instancia de la Core API y sesiones en memoria | Bajo | Aceptado para el MVP (3.4, 6.4) |
| R14 | Falta la muestra `.msg` para los tests | Bajo | Tests escritos y omitidos hasta tener la muestra (8.1) |

### 9.3 Mapa de cobertura de la spec

Cada historia, dónde se resuelve, en qué etapa y cómo se verifica:

| Historia | Plan | Etapa | Verificación |
|---|---|---|---|
| **HU1** Preguntar con fuentes e idioma | 2.3–2.4, 4.3 (`classify`, `retrieve`, `grade`, `generate`, `finalize`) | 1 | Grafo con LLM falso; evaluación `answerable` |
| **HU2** No sé y derivar | 4.3 (`find_referral`, `canned_reply`), 4.4 | 1 | Grafo con LLM falso; evaluación `referral`, `no_information`, `partial` |
| **HU3** Aislamiento entre personas | 3.2 (`persona_id` en `chunk`), 4.3 (`retrieve`), 4.5 | 1 | Integración del repositorio; evaluación `cross_persona` |
| **HU4** Carga y actualización | 5.1–5.5, 3.2; programación y botón: 6.3, 6.5 | 1 (carpetas, CLI) · 2 (programada y manual) | Unitarios de store y parsers; integración de ingesta |
| **HU5** Conversación con contexto | 3.3 (`conversation`, checkpoints), 4.3 (`standalone_query`) | 1 | Unitarios de retención; grafo con LLM falso |
| **HU6** Respuesta progresiva y tiempo máximo | 2.4 (`accepted`, `token`, `final`, `error`), 4.1, 4.7; front: 6.4, 6.6 | 1 · 2 (pantalla) | Integración del worker; tests del front |
| **HU7** Varias apps cliente | 2.1, 7.2 (tópicos y ACLs) | 1 | Integración con dos clientes |
| **HU8** Registro | 3.3 (`audit_entry`), 3.5, 6.3, 6.6 | 1 (registro) · 2 (pantalla) | Integración; tests de la Core API |
| **HU9** Perfil | 5.7, 3.2 (`persona`), 1.7 | 1 | Unitarios del perfil |
| **HU10** Interfaz web | 6 completa | 2 | Tests del front y de la Core API; humo |
| **HU11** Mensajes configurables | 1.3 (`messages.yaml`), 4.3 (`canned_reply`) | 1 | Unitarios de mensajes |
| **HU12** Fuentes externas | 5.4, 2.5, 3.4 (`source`), 6.3, 6.6 | 3 | Spike; integración de conectores; humo con fuentes reales |
| **HU13** Presentarse | 4.3 (`classify` → `canned_reply`), 4.5 (canario) | 1 | Grafo con LLM falso; evaluación `about_assistant` |
| **HU14** Solo con la base | 4.3, 4.4, 4.5 | 1 | Evaluación `out_of_scope`, `small_talk`, `no_information` |
| **HU15** Manipulación y datos | 4.1 (límites), 4.3 (`screen_input`, `finalize`), 4.5, 5.6, 6.6, 7 | 1 · 2 (front) | Unitarios de detectores; evaluación de ataques y `secret_leak` |

| Requisito no funcional / criterio | Plan |
|---|---|
| Idioma de la respuesta | 4.3 (`classify.language`), 4.6 |
| Tiempo máximo y primer fragmento | 4.7, 1.8, 8.6 |
| Configuración sin cambiar el sistema | 1.8, 4.8 |
| Documentación de interfaces | 2.7, 6.3 (D32, D33) |
| Privacidad | 4.5, 7.4, R7 |
| Disponibilidad (siempre activo) | 7.5 |
| Criterios de éxito 1–4 | 8.6 |
