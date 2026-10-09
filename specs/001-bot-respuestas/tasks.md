# Backlog: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** Aprobado (2026-10-09, Francisco Neyrotte)
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md) · **Decisiones:** [docs/decisiones.md](../../docs/decisiones.md)

## Cómo se usa

- **Estado de cada tarea:** `[ ]` pendiente · `[~]` en curso · `[x]` terminada.
- Se trabaja **una tarea por vez**, en orden, respetando las dependencias.
- **Toda tarea termina** con: linters en verde (`pre-commit run --all-files`), sus tests en verde y un
  commit propio. Eso no se repite en cada "Hecho cuando".
- Ninguna tarea usa la API key de OpenRouter salvo las de **cierre de etapa** (D41).
- Si al implementar algo aparece una decisión nueva o un cambio de diseño, se para, se acuerda y se
  actualiza el plan antes de seguir.

## Resumen

| Etapa | Tareas | Resultado |
|---|---|---|
| 1. Núcleo | T01–T29 | Bot completo por Kafka, probado por línea de comandos |
| 2. Core API y front | T30–T45 | Demo en el navegador |
| 3. Fuentes externas | T46–T53 | Conocimiento de Jira, Confluence y SharePoint |

---

## Etapa 1 — Núcleo

### Fundaciones

**[x] T01 — Base del repositorio**
- Plan: 1.1 · Decisiones: D02, D03
- `CLAUDE.md` (reglas del proyecto), `README.md`, `.editorconfig`, `.env.example`,
  `.pre-commit-config.yaml` con hooks genéricos (espacios, fin de archivo, YAML/JSON válidos, archivos grandes, claves privadas), `scripts/check.sh`.
- **Hecho cuando:** `pre-commit run --all-files` pasa y el hook se ejecuta en cada commit.

**[x] T02 — Esqueleto de agent-service**
- Plan: 1.3, 1.8 · Depende de: T01
- Proyecto uv, estructura de paquetes, configuración de Ruff y mypy estricto (y sus hooks en
  pre-commit), `settings.py` con todas las variables de 1.8, logs en JSON, `truststore`, pytest.
  Entry points registrados (todavía sin lógica).
- **Hecho cuando:** `uv run pytest` corre un test de humo y los linters de Python pasan.

**[x] T03 — Contrato AsyncAPI**
- Spec: HU6, HU7 · Plan: 1.2, 2, 3.6, 5.9 · Depende de: T01
- `contracts/asyncapi.yaml` (AsyncAPI 3.0) y los cinco JSON Schema, con ejemplos. Generación de los
  modelos Pydantic en `flock_agent/contracts/`. Comando para generar la documentación HTML.
- **Hecho cuando:** un test valida todos los ejemplos contra sus esquemas y los modelos generados se importan.

### Infraestructura

**[x] T04 — CA y certificados**
- Plan: 7.1 · Depende de: T01
- `infra/certs/generate.sh` (OpenSSL en contenedor) y `add-client.sh`.
- **Hecho cuando:** genera la CA y los certificados de 7.1, y `openssl verify` valida cada uno contra la CA.

**[x] T05 — Certificado raíz corporativo** — *no aplica por ahora*
- Plan: 7.8
- Exportar el certificado raíz de la red de Flock desde Windows a `infra/corp-ca/corp-root.crt`.
- **Hecho cuando:** el archivo existe, está fuera de git y `docs/notas-entorno.md` explica cómo regenerarlo.
- **Resultado (2026-10-09):** no se encontró inspección HTTPS, así que no hay certificado que exportar.
  `infra/corp-ca/` queda opcional (los Dockerfiles de T27 usan lo que haya) y `docs/notas-entorno.md`
  explica cómo exportarlo si la inspección vuelve.

**[x] T06 — Postgres con mTLS**
- Plan: 3.1, 7.3 · Depende de: T04
- Servicio en Compose, TLS, autenticación por certificado, `init.sql` con extensión, schemas, roles y permisos.
- **Hecho cuando:** cada rol se conecta con su certificado; sin certificado se rechaza; `agent` no puede escribir en `knowledge`.

**[x] T07 — Kafka con mTLS y ACLs**
- Plan: 7.2 · Depende de: T04
- Servicio KRaft en Compose, listener SSL con certificado obligatorio, contenedores `certs-init` y `kafka-init` (tópicos y ACLs).
- **Hecho cuando:** `docker compose up` deja todo sano; cada usuario puede solo lo de su tabla de ACLs; sin certificado se rechaza.

**[x] T08 — Conexiones de Python**
- Plan: 1.3 (`common/`) · Depende de: T02, T06, T07
- `tls.py`, `db.py` (pool asíncrono), `kafka.py` (productor y consumidor con aiokafka).
- **Hecho cuando:** tests de integración publican y consumen un mensaje y consultan la base.

### Conocimiento e ingesta

**[x] T09 — Schema `knowledge` y repositorio**
- Spec: HU3, HU4 · Plan: 3.2, 7.3 · Depende de: T08
- Migraciones (yoyo), repositorio de personas, documentos, fragmentos, estado de sync, corridas y `meta`.
  Reemplazo atómico por documento y candado de ingesta.
- **Hecho cuando:** tests de integración prueban el reemplazo atómico, el borrado en cascada y el candado.

**[x] T10 — Embeddings**
- Plan: 5.5 · Decisiones: D22 · Depende de: T02
- Interfaz `Embedder`, implementación con fastembed, caché del modelo, control de modelo en `meta` (reindexar si cambia).
- **Hecho cuando:** tests verifican dimensiones, lotes y la detección de cambio de modelo.

**[x] T11 — División en fragmentos**
- Plan: 5.5 · Depende de: T02
- **Hecho cuando:** tests cubren cortes por encabezado y párrafo, solapamiento, contexto `[título > sección]` y correos e issues.

**[ ] T12 — Ocultamiento de secretos**
- Spec: HU15.4 · Plan: 5.6 · Depende de: T02
- **Hecho cuando:** cada detector tiene casos que deben ocultarse y casos parecidos que no; se cuentan las ocultaciones.

**[x] T13 — Parsers de texto, HTML, PDF y Word**
- Spec: HU4.6, HU4.7 · Plan: 5.3 · Depende de: T02
- Detección de texto por contenido, HTML/XML, PDF (y escaneados), docx con títulos y tablas, límite de tamaño.
- **Hecho cuando:** tests con una muestra por formato en `tests/fixtures/`.

**[ ] T14 — Parsers de correo y adjuntos**
- Spec: HU4.6 · Plan: 5.3, 8.1 · Depende de: T13
- `.eml` y `.msg`, adjuntos como documentos hijos, un nivel de anidamiento.
- **Hecho cuando:** los tests de `.eml` pasan; los de `.msg` están completos y **omitidos** hasta que exista la muestra.

**[x] T15 — Conector de carpetas**
- Spec: HU4 · Plan: 5.2, 5.3 · Depende de: T13
- Interfaz `SourceConnector`, `FileStore`, `LocalFolderStore` y `FilesConnector`.
- **Hecho cuando:** tests de altas, cambios, bajas y archivos ignorados.

**[x] T16 — Perfil de persona**
- Spec: HU9 · Plan: 5.7 · Depende de: T02
- **Hecho cuando:** tests de creación por defecto, cambios detectados y YAML inválido.

**[x] T17 — Datos de ejemplo**
- Plan: 8.6 · Depende de: —
- `examples/knowledge/` con dos personas ficticias, todos los formatos, español e inglés, documentos
  envenenados y documentos con secretos.
- **Hecho cuando:** cada persona tiene contenido suficiente para 20 casos de evaluación y hay contenido que solo tiene la otra persona.

**[x] T18 — Pipeline de ingesta y CLI**
- Spec: HU4, HU9 · Plan: 5.1, 5.5, 5.8 · Depende de: T09–T12, T14–T17
- Recorrido completo de 5.1 (sin Kafka), resumen por persona, `flock-ingest run`.
- **Hecho cuando:** test de integración ingesta `examples/knowledge`; una segunda corrida no reprocesa nada; borrar un archivo lo quita de la base.
- **Nota (2026-10-09):** se hizo antes que T12 y T14, a pedido. Quedan como puntos de extensión marcados
  `TODO(T12)` (`knowledge/redaction.py` no oculta nada todavía) y `TODO(T14)` (los `.eml`/`.msg` se omiten).

### Agente

**[ ] T19 — Schema `agent` y repositorios**
- Spec: HU5, HU8, HU15.5 · Plan: 3.3 · Depende de: T08
- Migraciones, `conversation` (retención y generación), `processed_request`, `rate_limit_window`, `audit_entry`.
- **Hecho cuando:** tests de vencimiento por último mensaje, cambio de persona, idempotencia y ventana por minuto.

**[ ] T20 — LLM, mensajes y prompts**
- Spec: HU11 · Plan: 4.6, 4.7 · Depende de: T02
- Fábrica de modelos de OpenRouter, **LLM falso** para tests, `messages.yaml` con sus valores por
  defecto, prompts con versión y canario.
- **Hecho cuando:** tests de carga de mensajes con datos del perfil y del LLM falso con salida estructurada y streaming.

**[ ] T21 — Búsqueda híbrida**
- Spec: HU3 · Plan: 4.3 (`retrieve`), 4.8 · Depende de: T09, T10
- Vectorial + palabras + Reciprocal Rank Fusion, siempre filtrada por persona; búsqueda en las demás personas para derivar.
- **Hecho cuando:** tests de integración: encuentra por sentido y por término exacto, y nunca devuelve fragmentos de otra persona.

**[ ] T22 — Nodos de entrada**
- Spec: HU13, HU14, HU15.1 · Plan: 4.3 · Depende de: T20
- `screen_input`, `classify` y `canned_reply` (con adaptación de idioma).
- **Hecho cuando:** tests con LLM falso para cada intención y para patrones de manipulación (y preguntas legítimas que no deben marcarse).

**[ ] T23 — Nodos de respuesta**
- Spec: HU1, HU2 · Plan: 4.3 · Depende de: T21, T22
- `retrieve`, `grade`, `generate` (streaming) y `find_referral`.
- **Hecho cuando:** tests con LLM falso de respuesta completa, parcial, sin información y derivación (sin filtrar contenido de la otra persona).

**[ ] T24 — `finalize` y armado del grafo**
- Spec: HU1, HU15.6 · Plan: 4.2–4.5 · Depende de: T19, T23
- Citas, saneamiento de Markdown, canario, historial y checkpointer.
- **Hecho cuando:** un test por cada fila de la tabla 4.4 (cada `outcome`) recorre el grafo completo con LLM falso.

**[ ] T25 — Agent Worker**
- Spec: HU6, HU7, HU8, HU15 · Plan: 4.1, 4.7 · Depende de: T03, T24
- Consumo de pedidos, validaciones del worker, `accepted` / `token` / `final` / `error`, tiempo
  límite, concurrencia por conversación, confirmación de offsets, auditoría (tabla y `agent.audit`).
- **Hecho cuando:** tests de integración con LLM falso para un pedido normal, repetido, inválido,
  persona inexistente, pregunta larga, límite por app, tiempo agotado y dos apps a la vez.

**[ ] T26 — Cliente de prueba `flock-ask`**
- Spec: HU7 · Plan: 1.3 · Depende de: T25
- Envía una pregunta con el certificado `cli` y muestra la respuesta en streaming, las citas y la derivación.
- **Hecho cuando:** funciona contra el worker con LLM falso.

### Despliegue y cierre

**[ ] T27 — Imagen Python y servicios en Compose**
- Plan: 7.5 · Depende de: T05, T18, T25
- Dockerfile (agrega los `.crt` de `infra/corp-ca/` si existen), servicios `agent` e `ingestion`, volúmenes y healthchecks.
- **Hecho cuando:** `docker compose up` levanta todo y `flock-ingest run` + `flock-ask` funcionan contra los contenedores (con LLM falso).

**[ ] T28 — Evaluación (`flock-eval`)**
- Spec: criterios de éxito · Plan: 8.6 · Depende de: T17, T24
- `cases.yaml` (≥ 20 casos por persona, todas las categorías), verificaciones, LLM como juez,
  reporte, comparación de modelos.
- **Hecho cuando:** corre completo con el LLM falso (verificando la mecánica, no la calidad).

**[ ] T29 — Cierre de la etapa 1** ⚠️ usa la API key
- Plan: 8.5, 8.6, 9.1 · Depende de: T26–T28
- `scripts/smoke.sh`; evaluación con varios modelos de OpenRouter; elegir `LLM_MODEL` y
  `LLM_FAST_MODEL`; calibrar `REFERRAL_MIN_SCORE`; registrar resultados en `docs/`.
- **Hecho cuando:** humo en verde y la evaluación cumple los criterios de éxito (≥ 80 %, 100 %, 100 %), o hay un plan acordado para lo que no cumple.

---

## Etapa 2 — Core API y front

### Core API

**[ ] T30 — Esqueleto de core-api**
- Plan: 1.4 · Decisiones: D05, D32, D36 · Depende de: T03
- Maven, Spring Boot, Spotless y Checkstyle (y sus hooks), springdoc, Actuator, generación de clases desde `contracts/`.
- **Hecho cuando:** `mvn verify` pasa con un test de contexto.

**[ ] T31 — Conexiones de Java**
- Plan: 6.5, 7.2, 7.3 · Depende de: T30, T06, T07
- SSL bundles con los certificados, Kafka y Postgres con mTLS, Flyway con el schema `core`.
- **Hecho cuando:** tests de integración (Testcontainers) aplican las migraciones y publican y consumen mensajes.

**[ ] T32 — Autenticación**
- Spec: HU10.1 · Plan: 3.4, 6.2 · Depende de: T31
- `app_user`, usuario inicial desde variables de entorno, login, logout, `me`, cookie de sesión, CSRF, documentación pública.
- **Hecho cuando:** tests de login, `401` sin sesión, CSRF y acceso público a `/docs`.

**[ ] T33 — Copias de lectura**
- Spec: HU8, HU10 · Plan: 3.5, 6.5 · Depende de: T31
- Consumidores de `ingestion.events` (`persona_view`, `ingestion_run_view`) y `agent.audit` (`audit_entry_view`).
- **Hecho cuando:** tests verifican altas, cambios, bajas e idempotencia.

**[ ] T34 — Ingestion Worker con Kafka**
- Spec: HU4.8, HU4.9 · Plan: 5.1 · Decisiones: D31 · Depende de: T18, T08
- Consumo de `ingestion.jobs`, publicación de `ingestion.events` (incluye `rejected` y `persona_removed`).
- **Hecho cuando:** test de integración con un job, y con dos jobs simultáneos (el segundo se rechaza).

**[ ] T35 — Disparo de la ingesta**
- Spec: HU4.8 · Plan: 6.3, 6.5 · Depende de: T33, T34
- Scheduler cada `INGESTION_INTERVAL`, `POST /api/ingestion/runs`, `GET /api/ingestion/runs`.
- **Hecho cuando:** tests del scheduler y de los endpoints.

**[ ] T36 — Chat: de HTTP a Kafka**
- Spec: HU6, HU10 · Plan: 6.3, 6.4 · Depende de: T32
- `POST …/messages`, SSE `…/stream`, consumo de `agent.replies.core-api`, buffer para reconexión.
- **Hecho cuando:** test de punta a punta con un agente simulado: el SSE recibe `accepted`, `token` y `final`, y una reconexión recupera lo perdido.

**[ ] T37 — Personas, configuración y auditoría**
- Spec: HU8, HU10 · Plan: 6.3 · Depende de: T33
- `GET /api/personas`, `GET /api/config`, `GET /api/audit` paginado con filtros.
- **Hecho cuando:** tests de los endpoints y de cada filtro.

**[ ] T38 — Documentación publicada**
- Plan: 2.7, 6.3 · Depende de: T03, T30
- Swagger UI y AsyncAPI HTML servidos en `/docs`.
- **Hecho cuando:** ambas se ven sin sesión.

**[ ] T39 — Imagen de core-api**
- Plan: 7.5 · Depende de: T05, T31
- **Hecho cuando:** `core-api` corre en Compose y se conecta a Kafka y Postgres con su certificado.

### Front

**[ ] T40 — Esqueleto de web**
- Plan: 1.5, 6.7 · Depende de: T30
- Vite + React + TypeScript, ESLint, Prettier, `tsc` estricto, Vitest (y sus hooks), cliente generado
  del OpenAPI, tokens del design system de Flock, layout, ruteo y login.
- **Hecho cuando:** login funcional contra la Core API y tests del flujo de login.

**[ ] T41 — Pantalla de chat**
- Spec: HU6, HU10, HU15.6 · Plan: 6.6 · Depende de: T36, T37, T40
- Selector de persona, streaming, cuenta regresiva, citas, derivación, errores y reintento, Markdown
  seguro, contador de caracteres, conversación nueva.
- **Hecho cuando:** tests de cuenta regresiva, armado del streaming, Markdown seguro y errores.

**[ ] T42 — Pantalla de actualizaciones**
- Spec: HU4 · Plan: 6.6 · Depende de: T35, T40
- Botón "Actualizar ahora" e historial con el resumen de cada corrida (las fuentes externas se suman en la etapa 3).
- **Hecho cuando:** tests de la pantalla con API simulada.

**[ ] T43 — Pantalla de auditoría**
- Spec: HU8 · Plan: 6.6 · Depende de: T37, T40
- **Hecho cuando:** tests de filtros y detalle.

**[ ] T44 — Imagen de web**
- Plan: 6.1, 7.5 · Depende de: T05, T40
- Build con Node → nginx, proxy de `/api` y `/docs`.
- **Hecho cuando:** la demo completa funciona en `http://localhost:8080`.

**[ ] T45 — Cierre de la etapa 2** ⚠️ usa la API key
- Plan: 8.5, 8.6, 9.1 · Depende de: T41–T44
- Humo de punta a punta por el navegador y evaluación.
- **Hecho cuando:** humo en verde y la evaluación mantiene los criterios de éxito.

---

## Etapa 3 — Fuentes externas

**[ ] T46 — Spike: servidores MCP**
- Plan: 5.4 (riesgo R1) · Decisiones: D30
- Evaluar servidores MCP para Jira, Confluence y SharePoint: cuenta de servicio, JQL/CQL con
  paginación y comentarios, listado de archivos con autores.
- **Hecho cuando:** un documento en `docs/` con el resultado y la elección (MCP o API REST) para cada sistema, registrada en las decisiones.

**[ ] T47 — Administración de fuentes en la Core API**
- Spec: HU12.1, HU12.4 · Plan: 3.4, 6.3 · Depende de: T35
- Tabla `source`, endpoints, validación del `scope` y el `IngestionJob` con todas las fuentes.
- **Hecho cuando:** tests de alta, baja, validación y armado del job.

**[ ] T48 — Pantalla de fuentes**
- Spec: HU12.1 · Plan: 6.6 · Depende de: T42, T47
- **Hecho cuando:** tests de alta y baja con API simulada.

**[ ] T49 — Cliente MCP y servicios en Compose**
- Plan: 5.4, 7.5, 7.7 · Depende de: T46
- `McpClient` (paginación, reintentos), servidores MCP en el perfil `external-sources`, cuentas de servicio en `.env`.
- **Hecho cuando:** el Ingestion Worker se conecta a cada servidor y lista sus herramientas.

**[ ] T50 — Conector de Jira**
- Spec: HU12.2, HU12.3, HU12.7 · Plan: 5.4 · Depende de: T49
- **Hecho cuando:** tests con respuestas simuladas: filtro por reporter/assignee, comentarios incluidos, cambios incrementales y bajas.

**[ ] T51 — Conector de Confluence**
- Spec: HU12.2, HU12.3, HU12.7 · Plan: 5.4 · Depende de: T49
- **Hecho cuando:** tests con respuestas simuladas: filtro por creador/editor, conversión a Markdown, cambios y bajas.

**[ ] T52 — Conector de SharePoint**
- Spec: HU12.2, HU12.3, HU12.7 · Plan: 5.3, 5.4 · Depende de: T49
- `SharePointStore` reutilizando los parsers.
- **Hecho cuando:** tests con respuestas simuladas: filtro por autor, cambios y bajas.

**[ ] T53 — Cierre de la etapa 3** ⚠️ usa la API key
- Plan: 8.5, 9.1 · Depende de: T48, T50–T52
- Ingesta desde fuentes reales con las cuentas de servicio, preguntas que citan issues y páginas,
  quitar una fuente y verificar que su contenido desaparece, evaluación completa.
- **Hecho cuando:** humo en verde con fuentes reales y la evaluación mantiene los criterios de éxito.
