# infra

Entorno local con Docker Compose (plan, sección 7). Los comandos se corren desde la raíz del repo.

## Levantar

```bash
cp .env.example .env              # la primera vez: completar POSTGRES_ADMIN_PASSWORD (y los demás secretos cuando hagan falta)
docker compose up -d --wait
```

La primera vez, dos contenedores de un solo uso preparan todo:

- `certs-init` genera la CA propia y los certificados que falten (`infra/certs/out/`, fuera de git).
- `kafka-init` crea los tópicos y las ACLs (idempotente). Puede terminar unos segundos después de
  que `--wait` devuelve el control: `docker compose ps -a kafka-init` muestra `Exited (0)` al terminar.

## Servicios

| Servicio | Puerto en la PC | Detalle |
|---|---|---|
| `postgres` | `5433` | PostgreSQL 17 + pgvector. Solo TLS con certificado de cliente (7.3) |
| `kafka` | `9093` | Kafka 4 en modo KRaft. Solo TLS 1.3 con certificado de cliente; ACLs que prohíben todo por defecto (7.2) |
| `agent` | — | Agent Worker (`flock-agent`), imagen `agent-service/Dockerfile`. Sano cuando su bucle de Kafka está vivo |
| `ingestion` | — | Ingestion Worker (`flock-ingest worker`, consume `ingestion.jobs`), misma imagen. Sano cuando su bucle de Kafka está vivo |
| `core-api` | — | Core API (Spring Boot), imagen `core-api/Dockerfile`, en el puerto `8080` de la red de Docker. Sano cuando `/actuator/health` responde `UP` |

Dentro de la red de Docker, Kafka escucha en `kafka:9094`; desde la PC, en `localhost:9093`.

### Agente e ingesta en contenedores

```bash
LLM_PROVIDER=fake docker compose up -d --wait --build      # sin API key: respuestas fijas (D41)
KNOWLEDGE_HOST_DIR=../examples/knowledge docker compose run --rm ingestion flock-ingest run
```

- `LLM_PROVIDER`, `KNOWLEDGE_HOST_DIR` y los parámetros del agente se pueden fijar en `.env`. Sin
  `KNOWLEDGE_HOST_DIR` la ingesta lee `data/knowledge/`. Con el modelo real se definen
  `OPENROUTER_API_KEY` y `LLM_MODEL` en lugar de `LLM_PROVIDER=fake`.
- Cada contenedor recibe solo su certificado y sus variables. Arrancan como root solo para copiar
  su clave privada y preparar la caché del modelo, y después corren con el usuario `flock`.
- La primera vez, el agente descarga el modelo de embeddings (~0,2 GB) al volumen `embedding-models`,
  compartido con la ingesta; por eso su healthcheck tolera hasta 5 minutos de arranque.
- Para preguntarle: `flock-ask` desde la PC con el certificado `cli` (ver `agent-service/README.md`).
- La Core API no publica puertos en la PC: lo hará la web (nginx, T45). Mientras tanto, para usar el
  front con `npm run dev`, correrla en la PC (`./mvnw spring-boot:run`, ver `core-api/README.md`).
  Crea el usuario inicial con `ADMIN_USERNAME` y `ADMIN_PASSWORD` de `.env`.
- La imagen de la Core API genera la documentación AsyncAPI en su build (necesita bajar el generador
  con npm) y no corre los tests: esos van en `scripts/check.sh`.
- Si la red inspecciona HTTPS y fallan los builds: `infra/corp-ca/README.md`.

## Verificaciones

| Qué | Comando |
|---|---|
| Autenticación y permisos de Postgres | `infra/postgres/check.sh` |
| TLS, autenticación y ACLs de Kafka, con tráfico real | `infra/kafka/check.sh` |

`infra/kafka/check.sh` publica mensajes de prueba (`t07-probe-…`) en `agent.requests` y
`agent.replies.core-api`, y los consume con los grupos `agent` y `core-api`: quedan leídos.

## Apps cliente del agente

```bash
infra/certs/add-client.sh <clientId>    # certificado + tópico agent.replies.<clientId> + ACLs
```

## Administración

```bash
docker compose exec --user postgres postgres psql flock_ai   # superusuario, solo desde dentro del contenedor
docker compose down                                        # detener (los datos quedan en los volúmenes)
docker compose down --volumes                              # detener y borrar los datos
```

Los scripts de `infra/postgres/initdb/` solo corren cuando se crea el volumen de datos: si se
modifican, hay que borrar el volumen (`docker compose down --volumes`).

## Certificados

- `infra/certs/generate.sh`: crea lo que falte; nunca pisa lo existente. Para regenerar todo,
  borrar `infra/certs/out/` (y reiniciar los servicios).
- La identidad de cada servicio es el CN de su certificado:
  - Postgres la mapea a un rol en `infra/postgres/pg_ident.conf` (`core-api` → `core_api`).
  - Kafka la usa como usuario de las ACLs (`User:core-api`), con `ssl.principal.mapping.rules`.
- Los servicios que corren con un usuario sin privilegios (Postgres, Kafka) arrancan como root solo
  para copiar su clave privada con los permisos correctos, y después bajan de privilegios.
