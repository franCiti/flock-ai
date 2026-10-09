"""Fixtures of the integration tests (plan 8.1).

- integration_stack: against the Docker Compose stack (localhost:5433 and localhost:9093) with
  the real certificates of infra/certs/out/; skipped when the stack is not running.
- integration_containers: against ephemeral containers (Testcontainers); skipped without Docker.
"""

import socket
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest

from flock_agent.common.db import Pool, open_pool_with
from flock_agent.common.migrations import apply_migrations
from flock_agent.common.settings import Settings
from flock_agent.knowledge.repository import KnowledgeRepository
from tests.integration.containers import TestDatabase, docker_unavailable_reason, running_database

REPO_ROOT = Path(__file__).resolve().parents[3]
CERTS_DIR = REPO_ROOT / "infra" / "certs" / "out"
STACK_PORTS = {"PostgreSQL": 5433, "Kafka": 9093}


def _stack_unavailable_reason() -> str | None:
    if not CERTS_DIR.is_dir():
        return f"no certificates in {CERTS_DIR} (run: docker compose up -d --wait)"
    for name, port in STACK_PORTS.items():
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                pass
        except OSError:
            return f"{name} is not listening on localhost:{port} (run: docker compose up -d --wait)"
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    probes = {
        "integration_stack": _stack_unavailable_reason,
        "integration_containers": docker_unavailable_reason,
    }
    reasons: dict[str, str | None] = {}
    for item in items:
        for marker, probe in probes.items():
            if item.get_closest_marker(marker):
                if marker not in reasons:
                    reasons[marker] = probe()
                if (reason := reasons[marker]) is not None:
                    item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def test_database() -> Iterator[TestDatabase]:
    """One ephemeral PostgreSQL per test session, with the migrations of every schema applied."""
    with running_database() as database:
        apply_migrations(database.conninfo("ingestion"), schema="knowledge")
        apply_migrations(database.conninfo("agent"), schema="agent")
        yield database


async def _clean_pool(database: TestDatabase, role: str) -> Pool:
    return await open_pool_with(database.conninfo(role), max_size=2)


@pytest.fixture
async def knowledge(test_database: TestDatabase) -> AsyncIterator[KnowledgeRepository]:
    """Repository as the ingestion role, on an empty knowledge base."""
    pool = await _clean_pool(test_database, "ingestion")
    async with pool.connection() as connection:
        await connection.execute("TRUNCATE persona, ingestion_run, meta CASCADE")
    try:
        yield KnowledgeRepository(pool)
    finally:
        await pool.close()


@pytest.fixture
async def agent_pool(test_database: TestDatabase) -> AsyncIterator[Pool]:
    """Connections as the agent role (read-only on knowledge)."""
    pool = await _clean_pool(test_database, "agent")
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def agent_tables(agent_pool: Pool) -> Pool:
    """Connections as the agent role, on empty agent tables."""
    async with agent_pool.connection() as connection:
        await connection.execute(
            "TRUNCATE conversation, processed_request, rate_limit_window, audit_entry"
        )
    return agent_pool


StackSettings = Callable[..., Settings]


@pytest.fixture
def stack_settings() -> StackSettings:
    """Settings of a process that authenticates with the certificate `cert`."""

    def build(cert: str, *, postgres_user: str | None = None) -> Settings:
        cert_dir = CERTS_DIR / cert
        return Settings(
            _env_file=None,
            tls_cert_file=cert_dir / f"{cert}.crt",
            tls_key_file=cert_dir / f"{cert}.key",
            tls_ca_file=cert_dir / "ca.crt",
            postgres_user=postgres_user,
        )

    return build
