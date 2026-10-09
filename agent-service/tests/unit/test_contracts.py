"""The public contract: JSON Schemas, their examples and the generated Pydantic models."""

import filecmp
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft7Validator, FormatChecker
from pydantic import BaseModel, ValidationError

from flock_agent.contracts.generated.agent_reply_v1 import (
    AcceptedReply,
    AgentReply,
    ErrorReply,
    FinalReply,
    TokenReply,
)
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest
from flock_agent.contracts.generated.audit_entry_v1 import AuditEntry
from flock_agent.contracts.generated.ingestion_event_v1 import IngestionEvent
from flock_agent.contracts.generated.ingestion_job_v1 import IngestionJob

SERVICE_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = SERVICE_ROOT.parent / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
GENERATED_DIR = SERVICE_ROOT / "src" / "flock_agent" / "contracts" / "generated"

MODEL_BY_MESSAGE: dict[str, type[BaseModel]] = {
    "agent-request": AgentRequest,
    "agent-reply": AgentReply,
    "ingestion-job": IngestionJob,
    "ingestion-event": IngestionEvent,
    "audit-entry": AuditEntry,
}

EXAMPLES = sorted(EXAMPLES_DIR.glob("*/*.json"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validator_for(message: str) -> Draft7Validator:
    schema = load_json(SCHEMAS_DIR / f"{message}.v1.json")
    return Draft7Validator(schema, format_checker=FormatChecker())


def example_id(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def valid_request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = load_json(EXAMPLES_DIR / "agent-request" / "question.json")
    request.update(overrides)
    return request


# --- Schemas and examples -------------------------------------------------------------------


def test_every_message_has_examples() -> None:
    assert {path.parent.name for path in EXAMPLES} == set(MODEL_BY_MESSAGE)


@pytest.mark.parametrize("schema_path", sorted(SCHEMAS_DIR.glob("*.json")), ids=lambda p: p.name)
def test_schemas_are_valid_draft_07(schema_path: Path) -> None:
    Draft7Validator.check_schema(load_json(schema_path))


@pytest.mark.parametrize("example_path", EXAMPLES, ids=example_id)
def test_examples_match_their_schema(example_path: Path) -> None:
    validator_for(example_path.parent.name).validate(load_json(example_path))


@pytest.mark.parametrize("example_path", EXAMPLES, ids=example_id)
def test_examples_round_trip_through_the_generated_models(example_path: Path) -> None:
    raw = load_json(example_path)
    model_class = MODEL_BY_MESSAGE[example_path.parent.name]
    model = model_class.model_validate(raw)

    dumped = model.model_dump(mode="json", by_alias=True, exclude_unset=True)

    # Same fields with the same wire names, and the same meaning once parsed again
    # (the text may differ, e.g. "15:20:00.120Z" is written back as "15:20:00.120000Z").
    assert dumped.keys() == raw.keys()
    assert model_class.model_validate(dumped) == model


def test_asyncapi_references_existing_schemas() -> None:
    document = yaml.safe_load((CONTRACTS_DIR / "asyncapi.yaml").read_text(encoding="utf-8"))

    referenced = {
        message["payload"]["schema"]["$ref"]
        for message in document["components"]["messages"].values()
    }

    assert referenced == {f"./schemas/{path.name}" for path in SCHEMAS_DIR.glob("*.json")}


# --- Reply variants -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("example", "variant"),
    [
        ("accepted", AcceptedReply),
        ("token", TokenReply),
        ("final-answered", FinalReply),
        ("final-referral", FinalReply),
        ("error-timeout", ErrorReply),
        ("error-unreadable-request", ErrorReply),
    ],
)
def test_reply_type_selects_the_variant(example: str, variant: type[BaseModel]) -> None:
    reply = AgentReply.model_validate(load_json(EXAMPLES_DIR / "agent-reply" / f"{example}.json"))

    assert isinstance(reply.root, variant)


def test_python_field_names_are_snake_case() -> None:
    request = AgentRequest.model_validate(valid_request())

    assert request.persona_id == "juan-plataforma"
    assert request.reply_to == "agent.replies.core-api"


# --- Invalid messages -----------------------------------------------------------------------

INVALID_REQUESTS = {
    "unsupported version": {"version": 2},
    "request id is not a uuid": {"requestId": "not-a-uuid"},
    "persona id with uppercase": {"personaId": "Juan"},
    "empty question": {"question": ""},
    "reply topic of another channel": {"replyTo": "agent.requests"},
    "date without timezone": {"sentAt": "2026-10-09T15:20:00"},
    "non-string client context": {"clientContext": {"retries": 3}},
}


@pytest.mark.parametrize("overrides", INVALID_REQUESTS.values(), ids=INVALID_REQUESTS.keys())
def test_invalid_requests_are_rejected_by_schema_and_model(overrides: dict[str, Any]) -> None:
    request = valid_request(**overrides)

    assert not validator_for("agent-request").is_valid(request)
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(request)


@pytest.mark.parametrize("field", ["requestId", "conversationId", "personaId", "replyTo"])
def test_requests_without_required_fields_are_rejected(field: str) -> None:
    request = valid_request()
    del request[field]

    assert not validator_for("agent-request").is_valid(request)
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(request)


def test_unknown_fields_are_ignored() -> None:
    request = valid_request(priority="high")

    assert validator_for("agent-request").is_valid(request)
    assert "priority" not in AgentRequest.model_validate(request).model_dump(by_alias=True)


def test_reply_with_an_unknown_type_is_rejected() -> None:
    reply = load_json(EXAMPLES_DIR / "agent-reply" / "token.json")
    reply["type"] = "progress"

    assert not validator_for("agent-reply").is_valid(reply)
    with pytest.raises(ValidationError):
        AgentReply.model_validate(reply)


# --- Generated code -------------------------------------------------------------------------


def test_generated_models_are_up_to_date() -> None:
    # Generated inside the project so the code generator's formatter finds the same Ruff
    # configuration as the committed code.
    with tempfile.TemporaryDirectory(dir=SERVICE_ROOT, prefix="_codegen_check_") as output:
        subprocess.run(  # noqa: S603 (fixed command, no user input)
            [sys.executable, str(SERVICE_ROOT / "scripts" / "generate_contracts.py"), output],
            check=True,
        )

        comparison = filecmp.dircmp(GENERATED_DIR, output, ignore=["__pycache__"])
        assert comparison.left_only == []
        assert comparison.right_only == []
        assert comparison.diff_files == [], (
            "contracts changed: run `uv run python scripts/generate_contracts.py`"
        )
