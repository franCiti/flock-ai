# Arquitectura

Vista de alto nivel de flock-ai. Las decisiones y su motivo están en
[decisiones.md](decisiones.md) (referenciadas como `Dxx`).

> Documento de trabajo: la especificación del producto todavía no está cerrada.

**Idea central (D23):** el producto es el **agente**. Su API pública es un contrato de
mensajes en Kafka; cualquier app puede consumirlo. La app Java y el front son un cliente
más: están en el MVP para demostrarlo y administrar fuentes, pero el bot no depende de ellos.

**Orden de construcción (D27):** (1) núcleo: bot por Kafka + cliente CLI, (2) app Java + front,
(3) fuentes externas vía MCP.

## MVP — etapa 1: núcleo

```
  Apps cliente                     Cliente de prueba (CLI)
  (cualquiera, con su cert)        (el primer cliente, en el MVP)
          │                                   │
          │ publica en agent.requests          │      lee de agent.replies.<cliente>
          v                                   v                  ▲
 ┌─────────────────────────────────────────────────────────────┴───┐
 │                         Kafka (mTLS + ACLs)                     │
 └──────────────┬─────────────────────────────────────────▲────────┘
                v                                         │ tokens + respuesta final
 ┌─────────────────────────────────────────────────────────┴───────┐      ┌───────────────┐
 │  Agent Worker (Python 3.12 + LangGraph)                         │─TLS─>│ API de Claude │
 │  busca en la base de la persona · responde con citas o "no sé"  │      └───────────────┘
 │  memoria de conversación · auditoría                            │
 └──────────────┬──────────────────────────────────────────────────┘
                │ mTLS
                v
 ┌─────────────────────────────────────────────────────────────────┐
 │  PostgreSQL + pgvector     schema knowledge | schema agent      │
 └──────────────▲──────────────────────────────────────────────────┘
                │ mTLS
 ┌──────────────┴──────────────────┐      knowledge/
 │  Ingesta (comando manual, D29)  │<──── ├── juan-plataforma/   ← personaId = nombre de carpeta
 │  Python 3.12                    │      │   ├── deploy.md
 └─────────────────────────────────┘      │   └── accesos.pdf
                                          └── ana-datos/
                                              └── ...
```

### Componentes del MVP

| Componente | Lenguaje | Responsabilidad |
|---|---|---|
| **Agent Worker** | Python 3.12 / LangGraph | Consume `agent.requests`; busca solo en la base de la persona pedida; llama a Claude; responde con citas o dice que no sabe; publica tokens y respuesta final en el `replyTo`; guarda memoria de conversación y auditoría (D26) |
| **Ingesta** | Python 3.12 | Comando manual: recorre la carpeta raíz, una subcarpeta por persona; indexa archivos nuevos y modificados y quita los borrados (D29) |
| **Cliente de prueba** | Python 3.12 | CLI para enviar preguntas por Kafka y mostrar la respuesta, como lo haría cualquier app cliente |
| **Kafka** | — | Transporte del contrato público (D23–D25) |
| **PostgreSQL + pgvector** | — | `knowledge`: documentos, chunks, embeddings por persona. `agent`: checkpoints, historial, auditoría |

## Contrato del agente (D23, D24)

| Tópico | Quién publica → quién lee | Contenido | Clave |
|---|---|---|---|
| `agent.requests` | App cliente → Agent Worker | Pedido | `conversationId` |
| `agent.replies.<cliente>` | Agent Worker → esa app cliente | Tokens (agrupados), respuesta final con citas, errores | `conversationId` |

Pedido (ilustrativo; el esquema formal se define en el plan):

```json
{
  "version": 1,
  "requestId": "…",
  "conversationId": "…",
  "personaId": "juan-plataforma",
  "question": "¿Cómo hago rollback?",
  "replyTo": "agent.replies.app-x"
}
```

- `requestId`: correlación e idempotencia (un pedido repetido no se procesa dos veces).
- `conversationId`: memoria de la conversación y orden de los mensajes (clave de partición).
- Autorización: cada app cliente tiene su certificado; las ACLs de Kafka definen dónde puede
  publicar y qué tópico de respuesta puede leer (D25).

### Flujo de una pregunta

```
App cliente               Kafka                    Agent Worker               Postgres
    │── agent.requests ──>│─────────────────────────>│                            │
    │                     │                          │── historial (conversación)─>│
    │                     │                          │── búsqueda en la base ─────>│
    │                     │                          │   de la persona             │
    │                     │                          │── llama a Claude (stream)   │
    │<─ agent.replies.x ──│<──── tokens agrupados ───│                            │
    │<─ agent.replies.x ──│<──── respuesta final ────│── auditoría ──────────────>│
    │                     │      + citas             │                            │
```

## Seguridad en el MVP

| Tramo | Mecanismo |
|---|---|
| App cliente ↔ Kafka | mTLS con certificado de la app + ACLs por tópico (D17, D25) |
| Workers ↔ Kafka / Postgres | mTLS con certificados de la CA propia (D17) |
| Agent Worker → API de Claude | TLS estándar + API key (solo en el Agent Worker) |
| Aislamiento entre personas | El agente solo busca en la base del `personaId` del pedido (D18) |

## MVP — etapas 2 y 3: app Java, front y fuentes externas

```
 Frontend (React) ──cookie──> Core API (Java/Spring Boot) ──mTLS──> Kafka ──> Agent Worker
                               │  login (1 usuario, tabla)
                               │  administración de fuentes
                               │  SSE hacia el front
                               v
                         Ingesta (Python) ──cliente MCP──> servidores MCP de
                                                           Jira · Confluence · SharePoint
```

- **Core API (Java):** cliente del agente como cualquier otro (D23). Login con Spring Security y
  usuario en tabla (D16); guarda las fuentes de cada persona; retransmite las respuestas al front por SSE.
- **Frontend (React):** chat con cuenta regresiva y administración de fuentes (D10).
- **Fuentes externas vía MCP (D30):** la ingesta lee Jira, Confluence y SharePoint a través de
  servidores MCP, solo para construir la base. Cómo se dispara la ingesta desde la interfaz: abierto.

## Después del MVP

- **Tools** servidas por la Core API vía MCP, para tareas puntuales con aprobación humana (D13, D14).
- SSO y permisos por usuario sobre personas (D18).
- Correo como fuente directa.
