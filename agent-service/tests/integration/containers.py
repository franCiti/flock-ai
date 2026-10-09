"""Ephemeral PostgreSQL for tests (plan 8.1, marker integration_containers).

Same image as the Docker Compose stack and the same roles/schemas script
(infra/postgres/initdb), so privileges match production. TLS is not involved: these tests
cover logic on tables. Roles get a test password, since certificates are not used here.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

# Ryuk (Testcontainers' reaper container) fails to map its port on Docker Desktop for Windows.
# Containers are still stopped: they are always used as context managers.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from testcontainers.community.postgres import (
    PostgresContainer,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg17"
INIT_SCRIPTS = sorted((REPO_ROOT / "infra" / "postgres" / "initdb").glob("*.sql"))
TEST_PASSWORD = "test-only"  # noqa: S105 (throwaway container)


def docker_unavailable_reason() -> str | None:
    try:
        import docker

        docker.from_env().ping()
    except Exception as error:
        return f"Docker is not available ({type(error).__name__})"
    return None


class TestDatabase:
    __test__ = False  # not a test class, despite the name

    def __init__(self, container: PostgresContainer) -> None:
        self._container = container

    def conninfo(self, role: str) -> str:
        return make_conninfo(
            host=self._container.get_container_host_ip(),
            port=self._container.get_exposed_port(5432),
            dbname="flock_ai",
            user=role,
            password=TEST_PASSWORD,
            sslmode="disable",
        )


@contextmanager
def running_database() -> Iterator[TestDatabase]:
    with PostgresContainer(
        POSTGRES_IMAGE, dbname="flock_ai", username="admin", password=TEST_PASSWORD, driver=None
    ) as container:
        database = TestDatabase(container)
        with psycopg.connect(database.conninfo("admin"), autocommit=True) as connection:
            for script in INIT_SCRIPTS:
                connection.execute(script.read_text(encoding="utf-8"))
            for role in ("core_api", "ingestion", "agent"):
                connection.execute(
                    psycopg.sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        psycopg.sql.Identifier(role), psycopg.sql.Literal(TEST_PASSWORD)
                    )
                )
        yield database
