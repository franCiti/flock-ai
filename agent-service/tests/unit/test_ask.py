"""flock-ask: the request it sends and how it prints the replies (task T26)."""

import io
import json
from typing import Any

import pytest

from flock_agent.common.kafka import encode_message
from flock_agent.contracts.generated.agent_reply_v1 import AgentReply
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest
from flock_agent.tools.ask import REPLY_TOPIC, ReplyPrinter, build_parser, build_request

ENVELOPE: dict[str, Any] = {
    "version": 1,
    "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
    "conversationId": "c1",
    "personaId": "juan-plataforma",
    "sentAt": "2026-10-13T15:00:00Z",
}


def reply(kind: str, seq: int, **fields: Any) -> AgentReply:
    return AgentReply.model_validate({**ENVELOPE, "type": kind, "seq": seq, **fields})


def final(answer: str, **fields: Any) -> AgentReply:
    values: dict[str, Any] = {
        "answer": answer,
        "outcome": "answered",
        "persona": {"id": "juan-plataforma", "displayName": "Juan Pérez"},
        "citations": [
            {
                "documentId": "file:juan-plataforma:deploy.md",
                "title": "deploy.md",
                "path": "deploy.md",
                "section": "Rollback",
                "sourceType": "file",
            }
        ],
        "referral": {"id": "ana-datos", "displayName": "Ana Gómez"},
        "timing": {"firstTokenMs": 120, "totalMs": 900},
    }
    return reply("final", 3, **(values | fields))


def test_the_request_follows_the_contract() -> None:
    request = build_request("¿Cómo hago rollback?", "juan-plataforma", "c1")
    sent = json.loads(encode_message(request))
    assert AgentRequest.model_validate(sent) == request
    assert sent["replyTo"] == REPLY_TOPIC == "agent.replies.cli"
    assert sent["version"] == 1


def test_streamed_answer_with_sources_and_referral() -> None:
    out = io.StringIO()
    printer = ReplyPrinter(out)
    assert not printer.handle(reply("accepted", 0, deadlineAt="2026-10-13T15:02:00Z"))
    assert not printer.handle(reply("token", 1, text="Ejecutá rollback-prod "))
    assert not printer.handle(reply("token", 2, text="[1]."))
    assert printer.handle(final("Ejecutá rollback-prod [1]."))
    assert out.getvalue() == (
        "Ejecutá rollback-prod [1].\n"
        "Sources:\n"
        "  [1] deploy.md > Rollback (deploy.md)\n"
        "Suggested persona: Ana Gómez (ana-datos)\n"
        "[answered · Juan Pérez · first token 120 ms · total 900 ms]\n"
    )
    assert printer.exit_code == 0


def test_a_final_text_different_from_the_stream_replaces_it() -> None:
    out = io.StringIO()
    printer = ReplyPrinter(out)
    printer.handle(reply("token", 1, text="texto parcial"))
    printer.handle(final("Texto definitivo.", citations=[], referral=None))
    assert "--- final answer ---\nTexto definitivo." in out.getvalue()


def test_an_error_reply() -> None:
    out = io.StringIO()
    printer = ReplyPrinter(out)
    assert printer.handle(
        reply("error", 0, code="RATE_LIMITED", message="Demasiadas consultas.", retryable=True)
    )
    assert out.getvalue() == "Error RATE_LIMITED: Demasiadas consultas. (retry later)\n"
    assert printer.exit_code == 1


def test_the_persona_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["¿Hola?"])
    args = build_parser().parse_args(["--persona", "ana-datos", "¿Hola?"])
    assert (args.persona, args.question, args.conversation) == ("ana-datos", "¿Hola?", None)
