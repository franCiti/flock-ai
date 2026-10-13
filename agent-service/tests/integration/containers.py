"""Ephemeral PostgreSQL and Kafka for tests (plan 8.1, marker integration_containers).

Same image as the Docker Compose stack and the same roles/schemas script
(infra/postgres/initdb), so privileges match production. TLS and ACLs are not involved: these
tests cover logic on tables and messages (the Compose stack tests cover mTLS, T08). Roles get a
test password, since certificates are not used here.
"""

import os
import socket
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
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

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


KAFKA_IMAGE = "apache/kafka:4.3.1"  # same image as the Docker Compose stack


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@contextmanager
def running_kafka() -> Iterator[str]:
    """Single-node Kafka (KRaft) without TLS; yields its bootstrap address.

    The broker advertises the host port it is published on, so the port is chosen up front
    and mapped to the same number inside the container.
    """
    port = _free_port()
    container = (
        DockerContainer(KAFKA_IMAGE)
        .with_bind_ports(port, port)
        .with_env("KAFKA_NODE_ID", "1")
        .with_env("KAFKA_PROCESS_ROLES", "broker,controller")
        .with_env("KAFKA_LISTENERS", f"PLAINTEXT://:{port},CONTROLLER://:9093")
        .with_env("KAFKA_ADVERTISED_LISTENERS", f"PLAINTEXT://localhost:{port}")
        .with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")
        .with_env(
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP", "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT"
        )
        .with_env("KAFKA_CONTROLLER_QUORUM_VOTERS", "1@localhost:9093")
        .with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
        .with_env("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
        .with_env("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
        .with_env("KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", "0")
        .with_env("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "false")
        .waiting_for(LogMessageWaitStrategy("Kafka Server started").with_startup_timeout(60))
    )
    with container:
        yield f"localhost:{port}"
