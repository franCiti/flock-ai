# Plan técnico: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** En redacción (sección 1 de 9)
**Spec:** [spec.md](spec.md) (aprobada) · **Decisiones:** [docs/decisiones.md](../../docs/decisiones.md)

> El plan describe **cómo** se construye lo que pide la spec. Cada pieza indica qué historias
> (`HUxx`) cubre y qué decisiones (`Dxx`) aplica. Todo el código, nombres de archivos,
> paquetes y configuración van en **inglés** (D02).

## Índice

1. [Estructura del repositorio y de los servicios](#1-estructura-del-repositorio-y-de-los-servicios)
2. Contrato AsyncAPI — *pendiente*
3. Modelo de datos — *pendiente*
4. Grafo del agente — *pendiente*
5. Ingesta y conectores — *pendiente*
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
│   ├── agent-reply.v1.json   tokens, final answer, error (discriminated by "type")
│   ├── ingestion-job.v1.json
│   └── ingestion-event.v1.json
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
- **Pendiente para la sección 3:** las personas y el registro de auditoría viven en schemas de
  Python (`knowledge` y `agent`), y Java no puede leer tablas ajenas (D12). La sección 3 define
  cómo los obtiene: por eventos de Kafka hacia una copia local, o a través de una API.

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

*Pendiente.*

## 3. Modelo de datos

*Pendiente.*

## 4. Grafo del agente

*Pendiente.*

## 5. Ingesta y conectores

*Pendiente.*

## 6. Core API y front

*Pendiente.*

## 7. Seguridad e infraestructura

*Pendiente.*

## 8. Tests y evaluación

*Pendiente.*

## 9. Riesgos y mapa de cobertura de la spec

*Pendiente.*
