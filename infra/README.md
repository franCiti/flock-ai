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

Dentro de la red de Docker, Kafka escucha en `kafka:9094`; desde la PC, en `localhost:9093`.

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
docker compose exec postgres psql -U postgres flock_ai   # superusuario, solo desde dentro del contenedor
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
