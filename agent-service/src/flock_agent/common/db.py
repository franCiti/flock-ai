"""PostgreSQL connection pool with certificate authentication (plan section 7.3)."""

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool

from flock_agent.common.settings import Settings
from flock_agent.common.tls import TlsFiles


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


async def open_pool(
    settings: Settings, *, min_size: int = 1, max_size: int = 5
) -> AsyncConnectionPool[AsyncConnection]:
    """Open a pool and wait until its first connections are established (fails fast)."""
    pool: AsyncConnectionPool[AsyncConnection] = AsyncConnectionPool(
        conninfo(settings), min_size=min_size, max_size=max_size, open=False
    )
    await pool.open(wait=True, timeout=15)
    return pool
