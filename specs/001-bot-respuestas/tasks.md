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

**[x] T12 — Ocultamiento de secretos**
- Spec: HU15.4 · Plan: 5.6 · Depende de: T02
- **Hecho cuando:** cada detector tiene casos que deben ocultarse y casos parecidos que no; se cuentan las ocultaciones.
- **Nota (2026-10-14):** en las credenciales de URLs y los pares clave-valor (`password: …`,
  `Password=…;`) se oculta solo el **valor** y solo si parece un secreto: sin espacios, 6 caracteres o
  más y con dígitos, símbolos o mayúsculas internas (o 16 caracteres o más). Así "la contraseña: se
  pide al líder" no se toca. Los tokens con forma reconocible y las claves privadas se ocultan siempre.
  El texto de reemplazo sale de `messages.yaml` (`secret_placeholder`). Como el hash de contenido se
  calcula sobre el texto ya ocultado, la próxima ingesta reindexa los documentos que tenían secretos.

**[x] T13 — Parsers de texto, HTML, PDF y Word**
- Spec: HU4.6, HU4.7 · Plan: 5.3 · Depende de: T02
- Detección de texto por contenido, HTML/XML, PDF (y escaneados), docx con títulos y tablas, límite de tamaño.
- **Hecho cuando:** tests con una muestra por formato en `tests/fixtures/`.

**[x] T14 — Parsers de correo y adjuntos**
- Spec: HU4.6 · Plan: 5.3, 8.1 · Depende de: T13
- `.eml` y `.msg`, adjuntos como documentos hijos, un nivel de anidamiento.
- **Hecho cuando:** los tests de `.eml` pasan; los de `.msg` están completos y **omitidos** hasta que exista la muestra.
- **Nota (2026-10-14):** el correo se indexa como `email` con sus campos (asunto, de, para, cc, fecha,
  nombres de adjuntos) y el cuerpo (texto, o HTML convertido). Cada adjunto soportado es un documento
  `email_attachment` con `parent_id`; los no soportados se informan en el resumen como
  `<ruta>#attachment/<nombre>`. Dos adjuntos con el mismo nombre se distinguen como `nombre (2)`.
  Si un correo cambia y pierde un adjunto, el pipeline lo borra. `PARSERS_VERSION` pasa a 2: la
  próxima ingesta relee todo y toma los correos que antes se omitían. `extract-msg` tiene licencia
  **GPL** (estaba en el plan 1.3); a revisar si el servicio se distribuye fuera de la empresa.

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

**[x] T19 — Schema `agent` y repositorios**
- Spec: HU5, HU8, HU15.5 · Plan: 3.3 · Depende de: T08
- Migraciones, `conversation` (retención y generación), `processed_request`, `rate_limit_window`, `audit_entry`.
- **Hecho cuando:** tests de vencimiento por último mensaje, cambio de persona, idempotencia y ventana por minuto.
- **Nota (2026-10-09):** los repositorios exponen la limpieza (`purge_expired`, `purge`), pero la
  tarea periódica que la invoca y el borrado de checkpoints con el checkpointer de LangGraph se
  conectan en T24/T25. `processed_request` se registra **después** de publicar la respuesta (entrega
  "al menos una vez", plan 4.1).

**[x] T20 — LLM, mensajes y prompts**
- Spec: HU11 · Plan: 4.6, 4.7 · Depende de: T02
- Fábrica de modelos de OpenRouter, **LLM falso** para tests, `messages.yaml` con sus valores por
  defecto, prompts con versión y canario.
- **Hecho cuando:** tests de carga de mensajes con datos del perfil y del LLM falso con salida estructurada y streaming.
- **Nota (2026-10-09):** el LLM falso vive en `src` (`agent/fake_llm.py`), no en `tests`, porque
  T27 y T28 corren `flock-ask` y `flock-eval` con él. `messages.yaml` incluye `secret_placeholder`
  (plan 5.6), que usará T12. La versión de los prompts se calcula del texto (hash), así no se olvida subirla.

**[x] T21 — Búsqueda híbrida**
- Spec: HU3 · Plan: 4.3 (`retrieve`), 4.8 · Depende de: T09, T10
- Vectorial + palabras + Reciprocal Rank Fusion, siempre filtrada por persona; búsqueda en las demás personas para derivar.
- **Hecho cuando:** tests de integración: encuentra por sentido y por término exacto, y nunca devuelve fragmentos de otra persona.
- **Nota (2026-10-09):** RRF con k = 60. Cada resultado trae además su similitud coseno (absoluta):
  `REFERRAL_MIN_SCORE` se compara contra ella, porque el puntaje de RRF solo ordena dentro de una búsqueda.
  El umbral y la confirmación con el LLM se aplican en `find_referral` (T23).

**[x] T22 — Nodos de entrada**
- Spec: HU13, HU14, HU15.1 · Plan: 4.3 · Depende de: T20
- `screen_input`, `classify` y `canned_reply` (con adaptación de idioma).
- **Hecho cuando:** tests con LLM falso para cada intención y para patrones de manipulación (y preguntas legítimas que no deben marcarse).
- **Nota (2026-10-09):** los nodos son funciones `async` que reciben el estado y `Dependencies`
  (`graph/deps.py`); T24 los conecta al grafo. Si falla la adaptación de idioma de un mensaje fijo,
  se envía en español en lugar de un error. Un idioma que el clasificador no informa bien se toma como `es`.

**[x] T23 — Nodos de respuesta**
- Spec: HU1, HU2 · Plan: 4.3 · Depende de: T21, T22
- `retrieve`, `grade`, `generate` (streaming) y `find_referral`.
- **Hecho cuando:** tests con LLM falso de respuesta completa, parcial, sin información y derivación (sin filtrar contenido de la otra persona).
- **Nota (2026-10-13):** `generate` marca su llamada al LLM con el tag `answer_stream`: el worker (T25)
  publica solo esos tokens. La sugerencia de derivación de una respuesta parcial se agrega al final
  del `answer` (llega en el `final`, no como tokens). Si falla la confirmación de la derivación, no se
  sugiere a nadie en lugar de dar error. Sin fragmentos, `grade` da `none` sin llamar al LLM.

**[x] T24 — `finalize` y armado del grafo**
- Spec: HU1, HU15.6 · Plan: 4.2–4.5 · Depende de: T19, T23
- Citas, saneamiento de Markdown, canario, historial y checkpointer.
- **Hecho cuando:** un test por cada fila de la tabla 4.4 (cada `outcome`) recorre el grafo completo con LLM falso.
- **Nota (2026-10-13):** el checkpointer guarda el estado de cada conversación, pero solo `history`
  pasa de una pregunta a otra: cada pregunta entra con `turn_input`, que reinicia el resto (por eso las
  `flags` no usan un reducer de LangGraph). Las marcas `[n]` se renumeran por orden de aparición
  (`[k]` = `citations[k-1]`); las URL ajenas a las citas quedan como código, sin enlace. Si se filtra el
  canario, la respuesta pasa a ser el error general con `outcome` `no_information`. Los checkpoints solo
  deserializan tipos propios habilitados (`checkpoint_serializer`).

**[x] T25 — Agent Worker**
- Spec: HU6, HU7, HU8, HU15 · Plan: 4.1, 4.7 · Depende de: T03, T24
- Consumo de pedidos, validaciones del worker, `accepted` / `token` / `final` / `error`, tiempo
  límite, concurrencia por conversación, confirmación de offsets, auditoría (tabla y `agent.audit`).
- **Hecho cuando:** tests de integración con LLM falso para un pedido normal, repetido, inválido,
  persona inexistente, pregunta larga, límite por app, tiempo agotado y dos apps a la vez.
- **Nota (2026-10-13):**
  - **`LLM_PROVIDER=fake`** (nuevo, plan 1.8): un LLM falso de desarrollo que responde según el prompt
    (saludos → cortesía, "¿quién sos?" → presentación, el resto se responde con el primer fragmento).
    Permite correr el worker, `flock-ask` y `flock-eval` sin API key (D41, T26–T28).
  - **`MAX_CONCURRENT_REQUESTS`** (nuevo, `8`): pedidos atendidos a la vez; los de una conversación van
    de a uno y en orden. Los offsets se confirman en orden por partición, al terminar cada pedido.
  - El `requestId` se registra como procesado después de publicar la respuesta (también los rechazos).
  - Los tokens se agrupan cada 100 ms y retienen los últimos caracteres: el canario nunca se publica.
    Límite conocido: si el modelo vuelca el prompt, el texto anterior al canario sí puede salir como
    tokens (el `final` lo reemplaza por el error general).
  - Los mensajes de error van en español (con el LLM caído no se pueden adaptar al idioma).
  - Tests: el procesamiento contra Postgres (Testcontainers) cubre todos los casos; el recorrido por
    Kafka real (contenedor `apache/kafka`, sin TLS) cubre pedido normal, dos apps y offsets.
    Verificado también `flock-agent` contra Docker Compose (mTLS) con el LLM falso.

**[x] T26 — Cliente de prueba `flock-ask`**
- Spec: HU7 · Plan: 1.3 · Depende de: T25
- Envía una pregunta con el certificado `cli` y muestra la respuesta en streaming, las citas y la derivación.
- **Hecho cuando:** funciona contra el worker con LLM falso.
- **Nota (2026-10-13):** `flock-ask --persona X [pregunta]` (sin pregunta: modo interactivo, una
  conversación). Lee `agent.replies.cli` sin grupo y desde el final, así no mueve offsets ni muestra
  respuestas viejas. Probado con tests de integración (Kafka de Testcontainers) y a mano contra Docker
  Compose (mTLS) con `flock-agent` y `LLM_PROVIDER=fake`; instrucciones en `agent-service/README.md`.

### Despliegue y cierre

**[x] T27 — Imagen Python y servicios en Compose**
- Plan: 7.5 · Depende de: T05, T18, T25
- Dockerfile (agrega los `.crt` de `infra/corp-ca/` si existen), servicios `agent` e `ingestion`, volúmenes y healthchecks.
- **Hecho cuando:** `docker compose up` levanta todo y `flock-ingest run` + `flock-ask` funcionan contra los contenedores (con LLM falso).
- **Nota (2026-10-14):** imagen en dos etapas (`agent-service/Dockerfile`, contexto la raíz del repo,
  `.dockerignore` deja afuera `.env`, `data/` y las claves). Arranca como root solo para copiar su clave
  privada y dar la caché del modelo al usuario `flock`, y corre como `flock`. El healthcheck del agente
  mira un archivo de latido que el worker toca en cada vuelta (`HEARTBEAT_FILE`, nuevo). El servicio
  `ingestion` queda en el perfil `ingestion-worker` hasta la T34 (su worker no existe todavía) y se usa
  con `docker compose run --rm ingestion flock-ingest run`; `KNOWLEDGE_HOST_DIR` (nuevo) elige la carpeta.

**[x] T28 — Evaluación (`flock-eval`)**
- Spec: criterios de éxito · Plan: 8.6 · Depende de: T17, T24
- `cases.yaml` (≥ 20 casos por persona, todas las categorías), verificaciones, LLM como juez,
  reporte, comparación de modelos.
- **Hecho cuando:** corre completo con el LLM falso (verificando la mecánica, no la calidad).
- **Nota (2026-10-14):** 51 casos (26 de Juan, 25 de Ana), todas las categorías en cada persona; los
  hechos salen del inventario de `examples/README.md`. Un caso puede tener `previous` (preguntas
  anteriores de la misma conversación, HU5) y, en los ataques, varios `outcome` aceptables. El idioma
  se detecta por palabras frecuentes (español/inglés). El prompt del juez (`JUDGE`) no forma parte de
  `PROMPT_VERSION`. Sin `EVAL_JUDGE_MODEL`, el juez es el modelo rápido evaluado (avisa). Con
  `LLM_PROVIDER=fake` el juez también es falso: un hecho cuenta si la mayoría de sus palabras está en
  la respuesta. Corrido completo contra Docker Compose con el LLM falso: 19/51 casos (esperable).

**[x] T29 — Cierre de la etapa 1** ⚠️ usa la API key
- Plan: 8.5, 8.6, 9.1 · Depende de: T26–T28
- `scripts/smoke.sh`; evaluación con varios modelos de OpenRouter; elegir `LLM_MODEL` y
  `LLM_FAST_MODEL`; calibrar `REFERRAL_MIN_SCORE`; registrar resultados en `docs/`.
- **Hecho cuando:** humo en verde y la evaluación cumple los criterios de éxito (≥ 80 %, 100 %, 100 %), o hay un plan acordado para lo que no cumple.
- **Nota (2026-10-14):** cerrada con el humo en verde contra un modelo gratuito de OpenRouter
  (`nvidia/nemotron-3-super-120b-a12b:free`) y `REFERRAL_MIN_SCORE` calibrado en 0,40. La evaluación
  de calidad con LLM real quedó **pendiente**, acordado con Francisco: la cuenta gratuita permite 50
  pedidos por día y una corrida necesita ~250. Detalle y opciones en `docs/cierre-etapa-1.md`.

---

## Etapa 2 — Core API y front

### Core API

**[x] T30 — Esqueleto de core-api**
- Plan: 1.4 · Decisiones: D05, D32, D36, D42 · Depende de: T03
- Maven, Spring Boot, Spotless y Checkstyle (y sus hooks), springdoc, Actuator, records del contrato con su test (D42).
- **Hecho cuando:** `mvn verify` pasa con un test de contexto.
- **Nota (2026-10-09):** `jsonschema2pojo` no soporta `oneOf`/`allOf`, así que las clases del contrato
  son records escritos a mano verificados por `ContractTest` (D42). Spring Boot 4.1.1 (Jackson 3),
  springdoc 3.1.1, Maven Wrapper con Maven 3.9.16, Spotless con palantir-java-format. Los hooks de
  pre-commit llaman a Maven vía `scripts/run_maven.py`. `ContractTest` lee `../contracts` (propiedad
  `contracts.dir`): la imagen de T39 tendrá que incluir esa carpeta o saltear los tests.

**[x] T31 — Conexiones de Java**
- Plan: 6.5, 7.2, 7.3 · Depende de: T30, T06, T07
- SSL bundles con los certificados, Kafka y Postgres con mTLS, Flyway con el schema `core`.
- **Hecho cuando:** tests de integración (Testcontainers) aplican las migraciones y publican y consumen mensajes.
- **Nota (2026-10-15):** mTLS en el perfil `mtls`, que es el perfil por defecto (`application-mtls.yml`):
  SSL bundle de Spring con los PEM para Kafka y, para Postgres, `PemSslSocketFactory` (pgjdbc en
  Windows rechaza las claves que el grupo Administradores puede leer). Los tests usan el perfil `test`
  con Testcontainers inicializado con `infra/postgres/initdb` (Flyway corre como `core_api`).
  `MutualTlsStackTest` verifica mTLS real contra Docker Compose (Postgres y Kafka, ambos en verde); su
  parte de Kafka se omite con el motivo cuando Avast intercepta el TLS de Java a `localhost:9093`, algo
  intermitente en esta PC (detalle en `docs/notas-entorno.md`).
  `V1` solo documenta el schema `core`; las tablas llegan con sus tareas.

**[x] T32 — Autenticación**
- Spec: HU10.1 · Plan: 3.4, 6.2 · Depende de: T31
- `app_user`, usuario inicial desde variables de entorno, login, logout, `me`, cookie de sesión, CSRF, documentación pública.
- **Hecho cuando:** tests de login, `401` sin sesión, CSRF y acceso público a `/docs`; y en `web/`,
  `npm run test:api` pasa contra la Core API levantada (lo dejó la T40).
- **Además:** actualizar la copia del OpenAPI del front, regenerar sus tipos (`npm run generate:api`) y
  reemplazar los tipos escritos a mano de `web/src/api/auth.ts` (`TODO(T32)`). El front espera que
  `GET /api/auth/me` entregue la cookie `XSRF-TOKEN` aun sin sesión, y que el login no exija más
  que `{ username, password }`.
- **Nota (2026-10-15):** CSRF en modo SPA de Spring Security 7 con la cookie entregada en toda
  respuesta (también en un 401). Al iniciar sesión cambian el id de sesión y el token CSRF (el nuevo
  llega en la respuesta siguiente). El logout es el de Spring Security, por eso no figura en el OpenAPI
  y el front lo llama sin el cliente generado. `test:api` se corrió contra la Core API en la PC con un
  usuario temporal que después se borró: el `.env` no tiene `ADMIN_PASSWORD`.

**[x] T33 — Copias de lectura**
- Spec: HU8, HU10 · Plan: 3.5, 6.5 · Depende de: T31
- Consumidores de `ingestion.events` (`persona_view`, `ingestion_run_view`) y `agent.audit` (`audit_entry_view`).
- **Hecho cuando:** tests verifican altas, cambios, bajas e idempotencia.
- **Nota (2026-10-15):** `ingestion_run_view` guarda el resumen por persona como objeto indexado por
  `personaId` (aplicar dos veces el mismo evento da lo mismo) y suma el estado `requested` para T35
  (la corrida existe desde que la Core API publica el job). Un `started` repetido no reabre una corrida
  terminada y un mensaje viejo no pisa el nombre más nuevo de una persona. Los mensajes ilegibles se
  registran y se saltean. `MutualTlsStackTest` corre con los listeners apagados.

**[x] T34 — Ingestion Worker con Kafka**
- Spec: HU4.8, HU4.9 · Plan: 5.1 · Decisiones: D31 · Depende de: T18, T08
- Consumo de `ingestion.jobs`, publicación de `ingestion.events` (incluye `rejected` y `persona_removed`).
- **Hecho cuando:** test de integración con un job, y con dos jobs simultáneos (el segundo se rechaza).
- **Nota (2026-10-15):** los jobs corren como tareas concurrentes a propósito: uno toma el candado y
  los que llegan mientras tanto se rechazan enseguida, en lugar de esperar su turno. Un job ya
  procesado (reentregado) o ilegible se saltea. Las fuentes externas del job se ignoran con un aviso
  hasta la etapa 3 (`TODO(T49)`). En Compose el servicio `ingestion` ya no tiene perfil y tiene
  healthcheck por latido. `OffsetTracker` pasó a `common/kafka.py` (lo comparten los dos workers).

**[x] T35 — Disparo de la ingesta**
- Spec: HU4.8 · Plan: 6.3, 6.5 · Depende de: T33, T34
- Scheduler cada `INGESTION_INTERVAL`, `POST /api/ingestion/runs`, `GET /api/ingestion/runs`.
- **Hecho cuando:** tests del scheduler y de los endpoints.
- **Nota (2026-10-15):** la corrida queda como `requested` en `ingestion_run_view` apenas la Core API
  publica el job; si Kafka no lo confirma, pasa a `failed` y la API responde 503. El primer job
  programado sale un intervalo después de arrancar. El job todavía no lleva fuentes externas
  (`TODO(T47)`). `GET /api/ingestion/runs?limit=` (1–100, por defecto 20), del más nuevo al más viejo.

**[x] T36 — Chat: de HTTP a Kafka**
- Spec: HU6, HU10 · Plan: 6.3, 6.4 · Depende de: T32
- `POST …/messages`, SSE `…/stream`, consumo de `agent.replies.core-api`, buffer para reconexión.
- **Hecho cuando:** test de punta a punta con un agente simulado: el SSE recibe `accepted`, `token` y `final`, y una reconexión recupera lo perdido.
- **Nota (2026-10-15):** el id de cada evento SSE es `<requestId>:<seq>` (no solo el `seq`, ver plan
  6.4): así un navegador que se reconecta después de una pregunta nueva recibe el pedido nuevo entero.
  El nombre del evento es el `type` del mensaje y el dato es el `AgentReply` tal como llegó. Al abrir
  el stream se manda un comentario `connected` (confirma la conexión enseguida) y después uno cada
  20 s. Una pregunta nueva descarta lo guardado del pedido anterior y las respuestas de pedidos
  viejos no se reenvían. Lo guardado se olvida pasados `ANSWER_TIMEOUT` (por defecto 2 min) + 1 min.
  Al apagar, la Core API cierra los streams antes que el servidor web.

**[x] T37 — Personas, configuración y auditoría**
- Spec: HU8, HU10 · Plan: 6.3 · Depende de: T33
- `GET /api/personas`, `GET /api/config`, `GET /api/audit` paginado con filtros.
- **Hecho cuando:** tests de los endpoints y de cada filtro.
- **Nota (2026-10-15):** `GET /api/audit?page=&size=` (página desde 0, tamaño 1–100, por defecto 20),
  del más nuevo al más viejo, con `{ items, page, size, totalItems }`. Filtros, todos juntos:
  `personaId`, `from` (incluido) y `to` (excluido) en ISO 8601, `outcome` y `flag` (repetibles: vale
  cualquiera de los valores, con los nombres del contrato) y `referred` (si sugirió otra persona: los
  "casos marcados" de HU8.2 incluyen las derivaciones). Un valor desconocido responde 400.
  `GET /api/config` devuelve `{ maxQuestionChars }` (`MAX_QUESTION_CHARS`, el mismo límite que el agente).

**[x] T38 — Documentación publicada**
- Plan: 2.7, 6.3 · Depende de: T03, T30
- Swagger UI y AsyncAPI HTML servidos en `/docs`.
- **Hecho cuando:** ambas se ven sin sesión.
- **Nota (2026-10-15):** `/docs/` es un índice con enlaces a Swagger UI (`/docs/swagger-ui/index.html`),
  la documentación AsyncAPI (`/docs/asyncapi/`) y la especificación OpenAPI (`/docs/openapi`). Como
  `contracts/docs/` se genera y está fuera de git, Maven la copia a la aplicación solo si existe:
  `scripts/check.sh` corre `contracts/build-docs.sh` antes de los tests de `core-api`, y la imagen
  (T39) la genera en su build. Sin generarla, el test de AsyncAPI queda omitido.

**[x] T39 — Imagen de core-api**
- Plan: 7.5 · Depende de: T05, T31
- **Hecho cuando:** `core-api` corre en Compose y se conecta a Kafka y Postgres con su certificado.
- **Nota (2026-10-15):** imagen en tres etapas: Node genera la documentación AsyncAPI, Maven arma el
  jar (sin tests, Spotless ni Checkstyle: corren en `scripts/check.sh`, y los tests necesitan Docker)
  y la ejecución usa JRE 21 con el usuario `flock` (el entrypoint copia el certificado, como en
  agent-service). El build instala `unzip`: sin él, el Maven Wrapper baja el `.tar.gz` y falla el
  control del SHA-256 (que es del `.zip`). Healthcheck contra `/actuator/health` con bash (la imagen
  no trae curl). El servicio no publica puertos en la PC hasta la web (T45), según el plan 7.5. En
  Compose, las variables que lee Spring llevan su valor por defecto: una variable vacía no cuenta como
  ausente. Verificado en Compose: Flyway con `verify-full`, los tres consumidores de Kafka con sus
  particiones, `/docs/` y `/docs/asyncapi/` con 200 y `/api/**` con 401 sin sesión.

### Front

**[x] T40 — Esqueleto de web**
- Plan: 1.5, 6.7 · Depende de: T30
- Vite + React + TypeScript, ESLint, Prettier, `tsc` estricto, Vitest (y sus hooks), cliente generado
  del OpenAPI, tokens del design system de Flock, layout, ruteo y login.
- **Hecho cuando:** login funcional contra la Core API y tests del flujo de login.
- **Nota (2026-10-09):** se hizo antes que T31 y T32, a pedido. El login está programado contra los
  endpoints del plan 6.2 y 6.3 y sus tests usan una API simulada. La prueba contra la Core API real
  (`npm run test:api`) **falla hasta la T32**, que la incluye en su "hecho cuando". La copia del
  OpenAPI vive en `web/src/api/openapi.json` y la controla `OpenApiSnapshotTest` en `core-api`.

**[x] T41 — Pantalla de chat**
- Spec: HU6, HU10, HU15.6 · Plan: 6.6 · Depende de: T36, T37, T40
- Selector de persona, streaming, cuenta regresiva, citas, derivación, errores y reintento, Markdown
  seguro, contador de caracteres, conversación nueva.
- **Hecho cuando:** tests de cuenta regresiva, armado del streaming, Markdown seguro y errores.
- **Nota (2026-10-15):** el armado de la conversación es un reducer puro (`conversation.ts`) y el
  `EventSource` queda detrás de `openReplyStream`; los tests usan un `EventSource` falso (jsdom no
  tiene) y la API simulada con MSW. Los tipos de los mensajes del stream están escritos a mano en
  `api/chat.ts` (el OpenAPI describe el stream como texto). Agregados al plan: cambiar de persona
  empieza una conversación nueva; la derivación ofrece "Conversar con *X*" si la persona existe; sin
  `accepted` en 30 s, o sin respuesta 15 s después del plazo, el turno termina con error y
  "Reintentar"; si el `EventSource` se rinde (por ejemplo, sesión vencida) aparece "Reconectar" y se
  revisa la sesión. Las citas repetidas (mismo documento y sección) se muestran una vez y los enlaces
  solo se abren si son `http(s)`. Probado en el navegador contra el stack con el modelo gratuito.
  Dependencia nueva: `react-markdown` 10.1.0.

**[x] T42 — Pantalla de actualizaciones**
- Spec: HU4 · Plan: 6.6 · Depende de: T35, T40
- Botón "Actualizar ahora" e historial con el resumen de cada corrida (las fuentes externas se suman en la etapa 3).
- **Hecho cuando:** tests de la pantalla con API simulada.
- **Nota (2026-10-15):** `/sources` muestra el historial (las últimas 20) en una tabla con los totales
  y, por corrida, un "Detalle" con el resumen de cada persona, los archivos omitidos con su motivo,
  las personas quitadas y el motivo de un fallo o rechazo. Mientras hay una corrida pedida o en curso,
  el historial se relee cada 3 s y "Actualizar ahora" queda deshabilitado (HU4.9). Estilos
  compartidos nuevos en `global.css`: `.panel`, chips de estado y la tabla de datos del design system.
  Visto en el navegador contra el stack: el conteo "sin cambios" del agente sale en 0 cuando nada
  cambió (el conector de carpetas no recorre los archivos sin cambios); queda como tarea aparte.

**[x] T43 — Pantalla de auditoría**
- Spec: HU8 · Plan: 6.6 · Depende de: T37, T40
- **Hecho cuando:** tests de filtros y detalle.
- **Nota (2026-10-15):** barra de filtros con persona, desde/hasta (días locales completos, "hasta"
  incluido), resultado, marca y "Solo con derivación"; la marca "Pedidos rechazados" agrupa
  `rate_limited`, `question_too_long` e `invalid_request` (HU8.2). Tabla paginada de a 20, y al elegir
  una pregunta, su detalle: datos del pedido, modelo y versión del prompt, tiempos, pregunta, respuesta
  (con el mismo Markdown seguro del chat) y fuentes. Visto contra el stack: la Core API manda `null`
  en los campos vacíos aunque el OpenAPI los declara opcionales; el front lo tolera.

**[x] T44 — Imagen de web**
- Plan: 6.1, 7.5 · Depende de: T05, T40
- Build con Node → nginx, proxy de `/api` y `/docs`.
- **Hecho cuando:** la demo completa funciona en `http://localhost:8080`.
- **Nota (2026-10-15):** `nginxinc/nginx-unprivileged` (sin root, puerto 8080). `/api` sin buffer y
  con `proxy_read_timeout` de 1 h para el SSE; `/actuator` responde 404 desde afuera. Las páginas del
  front llevan CSP (solo este origen, sin imágenes externas ni frames) y otras cabeceras de seguridad;
  `/docs` no, porque la sirve la Core API con sus propios scripts. Probado en el navegador en
  `http://localhost:8080`: login, chat con el modelo gratuito (SSE a través de nginx), actualizaciones
  y auditoría, sin violaciones de CSP. Arreglado al probarlo: después de cerrar sesión, volver a entrar
  sin recargar daba 403 porque el logout borra la cookie CSRF; `login()` ahora la pide antes si falta,
  y la API simulada de los tests valida el CSRF como Spring. Los helpers de CSRF pasaron a
  `api/csrf.ts`.

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
