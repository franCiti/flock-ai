"""Database migrations with yoyo (plan section 7.3).

Each schema owner applies its own migrations at start-up: the Ingestion Worker for `knowledge`,
the Agent Worker for `agent`. yoyo keeps its bookkeeping tables inside that same schema.
"""

from pathlib import Path
from urllib.parse import quote, urlencode

from psycopg.conninfo import conninfo_to_dict
from yoyo import get_backend, read_migrations

MIGRATIONS_ROOT = Path(__file__).resolve().parents[1]


def migrations_dir(schema: str) -> Path:
    """Migrations of a schema, shipped inside the package (e.g. knowledge/migrations/)."""
    return MIGRATIONS_ROOT / schema / "migrations"


def migration_uri(conninfo: str, *, schema: str) -> str:
    """yoyo URI for a libpq connection string; extra parameters are passed to psycopg."""
    params = {key: str(value) for key, value in conninfo_to_dict(conninfo).items()}
    user = quote(params.pop("user", ""), safe="")
    password = params.pop("password", None)
    credentials = f"{user}:{quote(password, safe='')}" if password else user
    host = params.pop("host", "localhost")
    port = params.pop("port", "5432")
    dbname = quote(params.pop("dbname", ""), safe="")
    query = urlencode({**params, "schema": schema})
    return f"postgresql+psycopg://{credentials}@{host}:{port}/{dbname}?{query}"


def apply_migrations(conninfo: str, *, schema: str) -> list[str]:
    """Apply the pending migrations of `schema`; returns the ids applied (empty if none)."""
    backend = get_backend(migration_uri(conninfo, schema=schema))
    migrations = read_migrations(str(migrations_dir(schema)))
    with backend.lock():
        pending = backend.to_apply(migrations)
        backend.apply_migrations(pending)
    return [migration.id for migration in pending]
