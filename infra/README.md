# infra

Entorno local con Docker Compose (plan, sección 7). Los comandos se corren desde la raíz del repo.

## Primera vez

```bash
cp .env.example .env              # completar POSTGRES_ADMIN_PASSWORD (y los demás secretos cuando hagan falta)
infra/certs/generate.sh           # CA propia y certificados de cada servicio (infra/certs/out/, fuera de git)
docker compose up -d --wait
```

## Servicios

| Servicio | Puerto en la PC | Detalle |
|---|---|---|
| `postgres` | `5433` | PostgreSQL 17 + pgvector. Solo acepta TLS con certificado de cliente (7.3) |

## Verificaciones

| Qué | Comando |
|---|---|
| Autenticación y permisos de Postgres | `infra/postgres/check.sh` |

## Administración

```bash
docker compose exec postgres psql -U postgres flock_ai   # superusuario, solo desde dentro del contenedor
docker compose down                                        # detener (los datos quedan en el volumen)
docker compose down --volumes                              # detener y borrar los datos
```

Los scripts de `infra/postgres/initdb/` solo corren cuando se crea el volumen de datos: si se
modifican, hay que borrar el volumen (`docker compose down --volumes`).

## Certificados

- `infra/certs/generate.sh`: crea lo que falte; nunca pisa lo existente. Para regenerar todo,
  borrar `infra/certs/out/`.
- `infra/certs/add-client.sh <clientId>`: certificado para una app cliente nueva del agente.
- Postgres mapea el CN del certificado a un rol en `infra/postgres/pg_ident.conf`
  (`core-api` → `core_api`, `agent` → `agent`, `ingestion` → `ingestion`).
