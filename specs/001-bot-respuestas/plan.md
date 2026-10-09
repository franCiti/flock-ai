# Plan técnico: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** En redacción (secciones 1–5 de 9)
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
6. Core API y front — *pendiente*
7. Seguridad e infraestructura — *pendiente*
8. Tests y evaluación — *pendiente*
9. Riesgos y mapa de cobertura de la spec — *pendiente*

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
  lenguajes; los mismos hooks corren antes de cada commit. Pre-commit se ejecuta con `uvx`, sin instalación global.
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
- **Documentación:** springdoc genera OpenAPI y publica Swagger UI en `/swagger-ui` (D32).
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

*Pendiente.*

## 7. Seguridad e infraestructura

*Pendiente.*

## 8. Tests y evaluación

*Pendiente.*

## 9. Riesgos y mapa de cobertura de la spec

*Pendiente.*
