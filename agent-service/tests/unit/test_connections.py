import json
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from flock_agent.common.db import DatabaseConfigError, conninfo
from flock_agent.common.kafka import encode_message, message_headers
from flock_agent.common.settings import Settings
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest

TLS = {
    "tls_cert_file": Path("certs/agent.crt"),
    "tls_key_file": Path("certs/agent.key"),
    "tls_ca_file": Path("certs/ca.crt"),
}


def test_conninfo_uses_full_verification_and_the_client_certificate() -> None:
    settings = Settings(_env_file=None, postgres_user="agent", **TLS)  # type: ignore[arg-type]

    params = conninfo_to_dict(conninfo(settings))

    assert params["host"] == "localhost"
    assert params["port"] == "5433"
    assert params["dbname"] == "flock_ai"
    assert params["user"] == "agent"
    assert params["sslmode"] == "verify-full"
    assert params["ssl_min_protocol_version"] == "TLSv1.3"
    assert Path(str(params["sslcert"])) == TLS["tls_cert_file"]
    assert Path(str(params["sslkey"])) == TLS["tls_key_file"]
    assert Path(str(params["sslrootcert"])) == TLS["tls_ca_file"]
    assert "password" not in params


def test_conninfo_requires_a_role() -> None:
    settings = Settings(_env_file=None, **TLS)  # type: ignore[arg-type]

    with pytest.raises(DatabaseConfigError, match="POSTGRES_USER"):
        conninfo(settings)


def test_message_headers_name_the_schema() -> None:
    assert message_headers("agent-request.v1") == [
        ("content-type", b"application/json"),
        ("schema", b"agent-request.v1"),
    ]


def test_messages_are_encoded_with_wire_names_and_without_unset_fields() -> None:
    request = AgentRequest.model_validate(
        {
            "version": 1,
            "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
            "conversationId": "c-1",
            "personaId": "juan",
            "question": "¿Cómo hago rollback?",
            "replyTo": "agent.replies.cli",
            "sentAt": "2026-10-09T15:20:00Z",
        }
    )

    payload = json.loads(encode_message(request))

    assert payload["personaId"] == "juan"
    assert payload["question"] == "¿Cómo hago rollback?"
    assert "clientContext" not in payload
