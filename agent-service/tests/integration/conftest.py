"""Fixtures for tests against the Docker Compose stack (plan 8.1, marker integration_stack).

They connect to localhost:5433 (PostgreSQL) and localhost:9093 (Kafka) with the real
certificates of infra/certs/out/, and are skipped when the stack is not running.
"""

import socket
from collections.abc import Callable
from pathlib import Path

import pytest

from flock_agent.common.settings import Settings

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
    reason = _stack_unavailable_reason()
    if reason is None:
        return
    for item in items:
        if item.get_closest_marker("integration_stack"):
            item.add_marker(pytest.mark.skip(reason=reason))


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
