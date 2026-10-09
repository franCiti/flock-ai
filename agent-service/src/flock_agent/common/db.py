"""PostgreSQL connection pool with certificate authentication (plan section 7.3)."""

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

from flock_agent.common.settings import Settings
from flock_agent.common.tls import TlsFiles

Pool = AsyncConnectionPool[AsyncConnection]


class DatabaseConfigError(ValueError):
    """The database settings of the process are missing or incomplete."""


def conninfo(settings: Settings) -> str:
    """libpq connection string: TLS with full verification and our client certificate.

    libpq does its own TLS (it does not use Python's ssl module), so it reads the files directly.
    """
    if settings.postgres_user is None:
        msg = "missing database setting: POSTGRES_USER"
        raise DatabaseConfigError(msg)
    tls = TlsFiles.from_settings(settings)
    return make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        sslmode="verify-full",
        sslrootcert=str(tls.ca_file),
        sslcert=str(tls.cert_file),
        sslkey=str(tls.key_file),
        ssl_min_protocol_version="TLSv1.3",
        application_name="flock-agent-service",
    )


async def _configure_connection(connection: AsyncConnection) -> None:
    # Adapts pgvector's `vector` type (extension created in infra/postgres/initdb).
    await register_vector_async(connection)


async def open_pool_with(
    conninfo_string: str, *, min_size: int = 1, max_size: int = 5, register_vector: bool = True
) -> Pool:
    """Open a pool and wait until its first connections are established (fails fast).

    register_vector=False is only for connecting before the pgvector extension exists.
    """
    pool: Pool = AsyncConnectionPool(
        conninfo_string,
        min_size=min_size,
        max_size=max_size,
        configure=_configure_connection if register_vector else None,
        open=False,
    )
    await pool.open(wait=True, timeout=15)
    return pool


async def open_pool(
    settings: Settings, *, min_size: int = 1, max_size: int = 5, register_vector: bool = True
) -> Pool:
    """Pool for this process, authenticated with its certificate (see conninfo)."""
    return await open_pool_with(
        conninfo(settings), min_size=min_size, max_size=max_size, register_vector=register_vector
    )
