"""Command-line test client of the agent (`flock-ask`, plan 1.3, D27).

Sends questions to agent.requests as the client app `cli` (its certificate) and prints the
replies of agent.replies.cli: the answer while it streams, then its sources, the suggested
persona (referral) and the timing.

    flock-ask --persona juan-plataforma "¿Cómo hago un rollback?"
    flock-ask --persona juan-plataforma          # interactive: one conversation, empty line ends

The reply topic is read without a consumer group, starting at its end: the tool never moves
offsets and never shows replies of earlier runs.
"""

import argparse
import asyncio
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TextIO

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from flock_agent.common.aio import run_async
from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.kafka import encode_message, message_headers, start_consumer, start_producer
from flock_agent.common.settings import Settings
from flock_agent.contracts.generated.agent_reply_v1 import (
    AcceptedReply,
    AgentReply,
    ErrorReply,
    FinalReply,
    TokenReply,
)
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest

REQUESTS_TOPIC = "agent.requests"
CLIENT_ID = "cli"  # its certificate, reply topic and ACLs (infra/kafka/setup.sh)
REPLY_TOPIC = f"agent.replies.{CLIENT_ID}"
REQUEST_SCHEMA = "agent-request.v1"

# How long to wait for the agent to accept a request, and the margin after its deadline.
ACCEPT_TIMEOUT = timedelta(seconds=30)
DEADLINE_GRACE = timedelta(seconds=5)

EXIT_ERROR_REPLY = 1
EXIT_NO_REPLY = 2


def build_request(
    question: str, persona_id: str, conversation_id: str, reply_to: str = REPLY_TOPIC
) -> AgentRequest:
    return AgentRequest(
        version=1,
        request_id=uuid.uuid4(),
        conversation_id=conversation_id,
        persona_id=persona_id,
        question=question,
        reply_to=reply_to,
        sent_at=datetime.now(UTC),
    )


class ReplyPrinter:
    """Writes the replies of one request; `handle` returns True on the last one."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._streamed = ""
        self.exit_code = 0

    def handle(self, message: AgentReply) -> bool:
        reply = message.root
        if isinstance(reply, TokenReply):
            self._streamed += reply.text
            self._out.write(reply.text)
            self._out.flush()
            return False
        if isinstance(reply, FinalReply):
            self._final(reply)
            return True
        if isinstance(reply, ErrorReply):
            if self._streamed:
                self._out.write("\n")
            retry = " (retry later)" if reply.retryable else ""
            self._out.write(f"Error {reply.code}: {reply.message}{retry}\n")
            self.exit_code = EXIT_ERROR_REPLY
            return True
        return False  # accepted

    def _final(self, reply: FinalReply) -> None:
        if reply.answer != self._streamed:
            # The final text is the definitive one (plan 2.4): it replaces what was streamed.
            if self._streamed:
                self._out.write("\n\n--- final answer ---\n")
            self._out.write(reply.answer)
        lines = [""]
        if reply.citations:
            lines.append("Sources:")
            for number, citation in enumerate(reply.citations, start=1):
                where = str(citation.url) if citation.url else citation.path or ""
                section = f" > {citation.section}" if citation.section else ""
                lines.append(f"  [{number}] {citation.title}{section} ({where})")
        if reply.referral is not None:
            lines.append(f"Suggested persona: {reply.referral.display_name} ({reply.referral.id})")
        first = reply.timing.first_token_ms
        first_text = "-" if first is None else f"{first} ms"
        lines.append(
            f"[{reply.outcome} · {reply.persona.display_name} · first token {first_text}"
            f" · total {reply.timing.total_ms} ms]"
        )
        self._out.write("\n".join(lines) + "\n")
        self._out.flush()


class AskSession:
    """One conversation with the agent over Kafka."""

    def __init__(
        self,
        producer: AIOKafkaProducer,
        consumer: AIOKafkaConsumer,
        *,
        persona_id: str,
        conversation_id: str,
        out: TextIO,
        requests_topic: str = REQUESTS_TOPIC,
        reply_topic: str = REPLY_TOPIC,
    ) -> None:
        self._producer = producer
        self._consumer = consumer
        self._persona_id = persona_id
        self._conversation_id = conversation_id
        self._out = out
        self._requests_topic = requests_topic
        self._reply_topic = reply_topic

    async def ready(self) -> None:
        """Start reading the reply topic at its current end (before sending anything)."""
        await self._consumer.seek_to_end()
        for partition in self._consumer.assignment():
            await self._consumer.position(partition)

    async def ask(self, question: str) -> int:
        """Send a question and print its replies; returns the exit code."""
        request = build_request(
            question, self._persona_id, self._conversation_id, self._reply_topic
        )
        await self._producer.send_and_wait(
            self._requests_topic,
            encode_message(request),
            key=self._conversation_id.encode(),
            headers=message_headers(REQUEST_SCHEMA),
        )
        printer = ReplyPrinter(self._out)
        give_up = time.monotonic() + ACCEPT_TIMEOUT.total_seconds()
        while (remaining := give_up - time.monotonic()) > 0:
            batch = await self._consumer.getmany(timeout_ms=int(min(remaining, 0.5) * 1000))
            for records in batch.values():
                for record in records:
                    try:
                        message = AgentReply.model_validate_json(record.value or b"")
                    except ValidationError:
                        continue  # not a reply of this contract version
                    reply = message.root
                    if reply.request_id != request.request_id:
                        continue  # another run of the tool
                    if isinstance(reply, AcceptedReply):
                        deadline = reply.deadline_at + DEADLINE_GRACE
                        give_up = time.monotonic() + (deadline - datetime.now(UTC)).total_seconds()
                    if printer.handle(message):
                        return printer.exit_code
        self._out.write("\nNo reply from the agent in time. Is flock-agent running?\n")
        return EXIT_NO_REPLY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flock-ask", description="Ask the agent a question over Kafka (test client)."
    )
    parser.add_argument("--persona", required=True, help="persona id, e.g. juan-plataforma")
    parser.add_argument(
        "--conversation", help="conversation id to continue (default: a new conversation)"
    )
    parser.add_argument("question", nargs="?", help="the question; without it, interactive mode")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = bootstrap()
    conversation = args.conversation or f"cli-{uuid.uuid4()}"
    raise SystemExit(run_async(_run(settings, args.persona, conversation, args.question)))


async def _run(settings: Settings, persona: str, conversation: str, question: str | None) -> int:
    producer = await start_producer(settings, client_id=CLIENT_ID)
    consumer = await start_consumer(settings, REPLY_TOPIC, client_id=CLIENT_ID, group_id=None)
    try:
        session = AskSession(
            producer,
            consumer,
            persona_id=persona,
            conversation_id=conversation,
            out=sys.stdout,
        )
        await session.ready()
        if question is not None:
            return await session.ask(question)
        print(f"Conversation {conversation} with {persona}. Empty line to quit.")
        code = 0
        while line := (await asyncio.to_thread(input, "\n> ")).strip():
            code = await session.ask(line)
        return code
    finally:
        await consumer.stop()
        await producer.stop()
