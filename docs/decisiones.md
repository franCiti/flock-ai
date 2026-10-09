# Registro de decisiones

Decisiones técnicas del proyecto, con su motivo. Una decisión **aceptada** solo se
cambia agregando una nueva que la reemplace (y marcando la vieja como *reemplazada*).

Estados: **Aceptada** · **Propuesta** (sugerida, falta confirmar) · **Abierta** (sin decidir)
· **Post-MVP** (aceptada, pero se implementa después del MVP; ver D23 y D27)

> Documento de trabajo: la especificación del producto (primera etapa de SDD) todavía
> no está cerrada y puede generar cambios acá.

---

## Proceso y convenciones

### D01 — Metodología: Spec-Driven Development · Aceptada
Spec → plan → backlog → implementación, con aprobación explícita en cada fase.
**Motivo:** que el código se derive de una especificación acordada, y aprender la metodología.

### D02 — Idiomas · Aceptada
Conversación, specs y documentación en **español**. **Todo el código en inglés**
(identificadores, comentarios, docstrings, logs).

### D03 — Linters obligatorios · Aceptada
Template básico de linters por lenguaje; todo el código debe pasarlos.
- **Python:** Ruff (lint + formato) y mypy en modo estricto.
- **Java:** Spotless (formato) y Checkstyle.
- **TypeScript:** ESLint, Prettier y `tsc` en modo estricto.

Corren en **pre-commit hooks** y con un comando único que ejecuta todos.

---

## Arquitectura

### D04 — App Java + workers Python · Aceptada
La app principal (dominio, usuarios, API) es Java; el agente y la ingesta son workers Python.
**Motivo:** Java es el lenguaje fuerte del equipo; el ecosistema de agentes y RAG (LangGraph,
loaders, SDKs) está más maduro en Python. La velocidad no es el criterio: el cuello de
botella es la latencia del LLM.
**Alternativa descartada:** todo en Java (Spring AI / LangChain4j), más simple pero con menos ecosistema.
**Nota:** desde D23 la app Java es un cliente más del agente. Entra en el MVP como backend
del front y administrador de fuentes (D27).

### D05 — Stack Java: Java 21 + Spring Boot · Aceptada
Incluye Spring Security (D16) y Spring AI para el servidor MCP (D14).

### D06 — Stack Python: Python 3.12 + uv · Aceptada
uv gestiona versión de Python, entorno virtual y dependencias.

### D07 — Orquestación del agente: LangGraph · Aceptada

### D08 — LLM: vía OpenRouter, modelo configurable · Aceptada
El Agent Worker accede al modelo a través de **OpenRouter** (API compatible con OpenAI).
El modelo es **configuración**: se elige comparando modelos con el set de evaluación.
Requisitos del modelo elegido: streaming y tool calling.
La API key vive **solo** en el entorno del Agent Worker (archivo `.env`, nunca en el repo).
**Privacidad:** en la cuenta de OpenRouter se desactiva el registro de prompts y el uso de datos para entrenamiento.
*Reemplaza la propuesta original: Claude vía API de Anthropic (Claude sigue disponible a través de OpenRouter).*

### D09 — Comunicación: Kafka asíncrono, REST síncrono · Aceptada
- **Kafka:** lo que tarda o se puede reintentar (preguntas al agente, ingestas, comandos).
- **REST:** lo que necesita respuesta inmediata (front ↔ Java, tools del agente → Java).

**Motivo:** el front nunca espera al LLM; los workers escalan por particiones; los servicios quedan desacoplados.

### D10 — Frontend: React + TypeScript · Aceptada
Chat de demostración y administración de fuentes; usa el design system de Flock
(skill `.claude/skills/flock-design-system`).
Habla **solo** con la Core API (REST + SSE). Nunca con Python ni con el LLM.

### D11 — Streaming: token por token + evento final · Aceptada
La respuesta se emite token por token al tópico de respuesta del cliente (D24); al terminar,
un evento final con la respuesta completa y sus citas (es lo que se persiste). La app Java,
cuando exista, los retransmite al front por SSE.
El worker agrupa tokens (p. ej. cada 100 ms) para no publicar un mensaje de Kafka por token.

### D12 — Persistencia: PostgreSQL + pgvector, un schema por servicio · Aceptada
Una sola instancia de Postgres con schemas `core` (Java), `knowledge` (Ingestion Worker) y
`agent` (Agent Worker, incluye checkpoints de LangGraph).
**Regla:** ningún servicio lee tablas de otro; los datos ajenos se piden por API o evento.
En el MVP existen solo `knowledge` y `agent`; `core` llega con la app Java.

### D13 — El agente actúa solo a través de tools · Post-MVP
El Agent Worker no accede al schema `core`; para leer o modificar datos de negocio usa las tools de la Core API (D14).

### D14 — Tools del agente vía MCP · Post-MVP
La Core API expone las tools como **servidor MCP** (Spring AI, transporte HTTP); el Agent
Worker es cliente MCP y descubre las tools al iniciar.
Cada llamada lleva el `personaId` para que Java valide la acción.
**Motivo:** cada tool se define una sola vez, junto a la lógica de negocio; es el estándar
para agentes; permite probar las tools desde Claude Code o Claude Desktop.
**Alternativa descartada:** endpoints REST con wrappers escritos a mano en Python (tools definidas dos veces).
MCP es solo para las tools del agente: el front sigue con REST (D09).

### D15 — Multi-agente no requerido · Aceptada
El producto no lo necesita al inicio; puede incorporarse más adelante (supervisor + subagentes) con fines de aprendizaje.

---

## Seguridad

### D16 — Autenticación del usuario: Spring Security + cookie de sesión · Aceptada
Login con formulario y sesión por cookie (`HttpOnly`, `Secure`, `SameSite`).
Usuarios en **tabla** (no en memoria) para facilitar la migración a SSO.
MVP: **un solo usuario**. A futuro: proveedor de SSO.

### D17 — Comunicación interna: mTLS con CA propia · Aceptada
Todas las conexiones internas usan certificado de cliente: apps cliente ↔ Kafka,
Python ↔ Kafka, Python ↔ Postgres y, post-MVP, Java ↔ Kafka, Java ↔ Postgres y Python → Core API (MCP).
Los certificados de cada servicio los firma una **CA propia** (autofirmada).
**Motivo:** cada servicio confía en una sola CA; sumar servicios no obliga a tocar los demás.
**Excepción:** la llamada al LLM (OpenRouter) sale a internet con TLS estándar + API key.

### D18 — Permisos por persona virtual · Aceptada (validación de usuarios: Post-MVP)
El permiso se otorga sobre la **base de conocimiento completa** de una persona virtual, no por documento.
En el MVP no hay usuarios: cualquier pregunta es válida y el acceso se controla por app cliente (D25).
- Cada documento indexado pertenece a una persona virtual (`personaId`).
- El agente solo busca en la base de la persona indicada en el pedido (aislamiento entre personas, ya en el MVP).
- Java valida el acceso usuario → persona antes de publicar el pedido; el agente solo busca en esa base.
- MVP: un usuario con acceso a una persona. A futuro: el SSO define qué usuarios acceden a qué personas.

---

## Conocimiento (RAG)

### D19 — Ingesta con interfaz común de conectores · Aceptada
Cada fuente implementa la misma interfaz y produce documentos normalizados; el pipeline
(chunking, embeddings, guardado) no sabe de dónde viene cada documento.
Fuentes previstas: archivos, Confluence, Jira, mail (el mail al final, por ser sensible).

### D20 — Fuente archivos: carpeta local y SharePoint · Aceptada
Se separa **dónde viven** los archivos (store: carpeta local o SharePoint vía MCP (D30), con sync
incremental de cambios y bajas) de **cómo se leen** (parsers por tipo: texto, pdf, docx, msg...).
*Separación: Propuesta.*

### D21 — RAG vs. consulta en vivo · Reemplazada por D30
Proponía consultar en vivo los datos que cambian. En el MVP las fuentes externas solo alimentan la base.

### D22 — Embeddings locales · Aceptada
Modelo local multilingüe (fastembed), sin API key, en desarrollo y en el MVP desplegado.
Detrás de una interfaz: se puede cambiar por un proveedor externo sin tocar el resto.

---

## Enfoque MVP

### D23 — El agente es el producto; su contrato en Kafka es su API pública · Aceptada
Cualquier app puede consumir el bot publicando en Kafka, sin pasar por la app Java.
La app Java y el front son un cliente más.
El formato de los mensajes es un **contrato versionado** (campo `version` + esquema formal);
no se cambia de forma incompatible sin una versión nueva.

### D24 — Request–reply sobre Kafka · Aceptada
Los pedidos van a `agent.requests` e indican en `replyTo` el tópico donde el cliente
quiere las respuestas (uno por app cliente: `agent.replies.<cliente>`).
Cada pedido lleva `requestId` (idempotencia y correlación) y `conversationId`.

### D25 — Autorización de apps cliente por ACL de Kafka · Aceptada
Cada app cliente se identifica con su certificado mTLS (D17). Las ACLs de Kafka definen
quién puede publicar en `agent.requests` y quién puede leer cada `agent.replies.<cliente>`.

### D26 — Historial y auditoría en el agente · Aceptada
El agente recuerda cada conversación por `conversationId` (checkpointer de LangGraph) y
registra pregunta, respuesta y fuentes en su schema `agent`. Ningún cliente necesita
implementar memoria.

### D27 — Alcance del MVP · Aceptada
**Incluye:** ingesta desde carpetas y desde Jira, Confluence y SharePoint (D30); agente que
responde con citas, dice que no sabe y deriva; contrato Kafka; cliente de prueba por línea de
comandos; app Java (backend del front, login de un usuario, administración de fuentes) y front React.
**Después:** tools para ejecutar tareas (D13, D14), SSO y permisos por usuario, correo como fuente directa.
**Orden de construcción propuesto:** (1) bot por Kafka + cliente CLI, (2) app Java + front,
(3) fuentes externas vía MCP.

### D28 — El bot está siempre activo · Aceptada
Responde siempre que el servicio esté levantado; no hay lógica de disponibilidad o ausencia del empleado.

### D29 — Ingesta del MVP: carpeta por persona · Aceptada (disparo: reemplazado por D31)
Una carpeta raíz con **una subcarpeta por persona virtual**; el nombre de la subcarpeta es el `personaId`.
*Originalmente:* comando manual y sin Kafka. Ver D31.

### D30 — Jira, Confluence y SharePoint se leen vía MCP, solo para ingesta · Aceptada
La ingesta usa clientes MCP contra servidores MCP de cada sistema para leer su contenido y
construir la base de conocimiento. Cada uno es una implementación más de la interfaz de
conectores (D19). El agente **no** consulta estas fuentes en vivo mientras responde.
**Riesgo a evaluar en el plan:** los servidores MCP están pensados para consultas puntuales de
un agente; hay que verificar que permitan recorrer todo el contenido y detectar cambios y bajas
(sync incremental). Si alguno no lo permite, ese conector puede usar la API del sistema directamente
sin cambiar la interfaz.
**Autoría:** solo se toma lo escrito por la persona (Confluence: páginas que creó o editó;
SharePoint: autora; Jira: reporter o assignee, con descripción y todos los comentarios). Para filtrar, el perfil de la persona guarda su identidad en esos sistemas (email).

### D31 — Disparo de la ingesta: cada 30 min y manual · Aceptada (mecanismo: Propuesta)
**Comportamiento (Aceptado):** automática cada 30 minutos (configurable) y manual desde la interfaz;
nunca dos ejecuciones simultáneas. El comando manual se mantiene para desarrollo.
**Mecanismo (Propuesta):** la Core API es dueña de las fuentes, así que también programa la ingesta:
un scheduler de Spring y el botón de la interfaz publican en `ingestion.jobs`; el Ingestion Worker
consume, procesa y publica el resultado en `ingestion.events`. Reemplaza el "sin Kafka" de D29.

### D32 — Documentación de la API REST: OpenAPI + Swagger UI · Aceptada
La Core API genera su especificación OpenAPI desde el código (springdoc-openapi) y publica Swagger UI.
**Motivo:** la API REST es interna (front ↔ Java); generarla desde el código evita que la doc quede desactualizada.

### D33 — Documentación del contrato Kafka: AsyncAPI, contract-first · Aceptada
El contrato público del agente (D23) se escribe **primero**, como especificación **AsyncAPI**
(el equivalente a OpenAPI para mensajería) con los payloads en **JSON Schema**, dentro del repo
(`contracts/`). De ese archivo se genera la documentación HTML navegable.
Java y Python validan los mensajes contra esos mismos esquemas.
**Motivo:** a diferencia de la API REST, este contrato es **público** y lo implementan dos lenguajes;
escribirlo primero lo convierte en la fuente de verdad, en lugar de que lo defina el código de uno de los dos.
**Alternativa:** Springwolf (genera AsyncAPI desde el código Spring, con UI similar a Swagger),
pero documentaría solo el lado Java.

### D39 — Fuentes externas con cuentas de servicio · Aceptada
Jira, Confluence y SharePoint se leen con una cuenta de servicio por sistema, configurada en el
`.env` del Ingestion Worker. Las credenciales no viajan por Kafka, no se guardan en la base y la
interfaz no las maneja. El filtro por autor (D30) limita el contenido de cada persona.

### D40 — Excepción a D17: servidores MCP sin mTLS · Aceptada
La conexión Ingestion Worker → servidores MCP (software de terceros, en general sin soporte de mTLS)
va sin certificado de cliente, solo dentro de la red interna de Docker y sin puertos expuestos.
**Alternativa descartada:** un proxy con mTLS delante de cada servidor MCP (un contenedor más por servidor).

---

## Organización y entrega

### D34 — SDD manual, compatible con Spec Kit · Aceptada
Cada feature vive en `specs/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md`.

### D35 — Monorepo · Aceptada
```
contracts/       AsyncAPI + JSON Schema (contrato público del agente)
agent-service/   Python: un proyecto, dos procesos (agente e ingesta)
core-api/        Java (Maven)
web/             React + TypeScript
infra/           Docker Compose, scripts de CA y certificados
docs/  specs/
```

### D36 — Build de Java: Maven · Aceptada

### D37 — Despliegue del MVP: local con Docker Compose · Aceptada
Todo levanta con un comando: Kafka (modo KRaft), Postgres + pgvector y los servicios. La nube queda para después.

### D38 — Estrategia de tests · Aceptada
- **Python:** pytest.
- **Java:** JUnit 5 + Testcontainers (Kafka y Postgres reales).
- **React:** Vitest.
- **Evaluación:** un runner del set de evaluación que mide los criterios de éxito de la spec y permite comparar modelos (D08).

---

## Abiertas
- Despliegue fuera del entorno local.
