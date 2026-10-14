"""What the Agent Worker does with one request (plan 4.1).

    1. validate against the schema -------------------> error INVALID_REQUEST / UNSUPPORTED_VERSION
    2. requestId already processed? -----------------> ignored
    3. limit per client app -------------------------> error RATE_LIMITED
    4. length of the question -----------------------> error QUESTION_TOO_LONG
    5. does the persona exist? ----------------------> error PERSONA_NOT_FOUND
    6. resolve the conversation (retention, persona change)
    7. publish accepted { deadlineAt }
    8. run the graph within ANSWER_TIMEOUT, streaming tokens --> error TIMEOUT / LLM_UNAVAILABLE
    9. publish final or error
   10. audit (table + agent.audit)

Steps 2 to 10 of one conversation run one request at a time and in order. The request id is
recorded as processed only after its reply is published (delivery "at least once").
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import openai
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from pydantic import AnyUrl, BaseModel, ValidationError

from flock_agent.agent.audit import AuditLog
from flock_agent.agent.conversations import ConversationStore
from flock_agent.agent.graph.answer import ANSWER_STREAM_TAG
from flock_agent.agent.graph.builder import Graph
from flock_agent.agent.graph.state import AgentState, Flag, PersonaRef, turn_input
from flock_agent.agent.idempotency import ProcessedRequests
from flock_agent.agent.messages import ErrorCode, Messages
from flock_agent.agent.prompts import PROMPT_VERSION, contains_canary, new_canary
from flock_agent.agent.rate_limit import RateLimiter
from flock_agent.contracts.generated import agent_reply_v1 as reply
from flock_agent.contracts.generated import audit_entry_v1 as audit
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest
from flock_agent.knowledge.models import Persona

log = logging.getLogger(__name__)

AUDIT_TOPIC = "agent.audit"
REPLY_SCHEMA = "agent-reply.v1"
AUDIT_SCHEMA = "audit-entry.v1"
REPLY_TOPIC_PREFIX = "agent.replies."

# Tokens are grouped so that Kafka does not get one message per token (D11).
TOKEN_FLUSH_SECONDS = 0.1

RETRYABLE: dict[ErrorCode, bool] = {
    "INVALID_REQUEST": False,
    "UNSUPPORTED_VERSION": False,
    "PERSONA_NOT_FOUND": False,
    "QUESTION_TOO_LONG": False,
    "RATE_LIMITED": True,
    "TIMEOUT": True,
    "LLM_UNAVAILABLE": True,
    "INTERNAL_ERROR": True,
}
_FLAGS: dict[ErrorCode, Flag] = {
    "INVALID_REQUEST": "invalid_request",
    "UNSUPPORTED_VERSION": "invalid_request",
    "QUESTION_TOO_LONG": "question_too_long",
    "RATE_LIMITED": "rate_limited",
}
_REPLY_TO = re.compile(r"^agent\.replies\.[a-z0-9-]{1,64}$")
_MAX_CONTEXT_PAIRS = 10  # clientContext limit of the contract

# Errors of the model provider that mean "the LLM did not answer" (plan 4.7).
_LLM_UNAVAILABLE = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
    ConnectionError,
)
# The provider refuses every request: bad key (401), no credits (402), forbidden (403). Not a bug
# of the request: the operator has to fix the account, and the client may retry later.
_PROVIDER_ACCOUNT_ERRORS = frozenset({401, 402, 403})


def is_llm_unavailable(error: Exception) -> bool:
    if isinstance(error, _LLM_UNAVAILABLE):
        return True
    return (
        isinstance(error, openai.APIStatusError) and error.status_code in _PROVIDER_ACCOUNT_ERRORS
    )


class Publisher(Protocol):
    async def publish(
        self, topic: str, key: str | None, message: BaseModel, schema: str
    ) -> None: ...


class PersonaDirectory(Protocol):
    """Read access to the personas of the knowledge base (KnowledgeRepository)."""

    async def get_persona(self, persona_id: str) -> Persona | None: ...


def client_id_of(reply_to: str) -> str:
    """'agent.replies.core-api' -> 'core-api' (plan 2.1)."""
    return reply_to.removeprefix(REPLY_TOPIC_PREFIX)


@dataclass(frozen=True)
class Envelope:
    """What every reply repeats from the request; fields that could not be read are None."""

    reply_to: str | None
    request_id: UUID | None = None
    conversation_id: str | None = None
    persona_id: str | None = None
    client_context: dict[str, str] | None = None

    @property
    def client_id(self) -> str | None:
        return None if self.reply_to is None else client_id_of(self.reply_to)

    @classmethod
    def salvage(cls, data: object) -> "Envelope":
        """The readable fields of an invalid request, so that it can still get an error."""
        if not isinstance(data, dict):
            return cls(reply_to=None)

        def text(name: str, max_length: int) -> str | None:
            value = data.get(name)
            return value if isinstance(value, str) and 0 < len(value) <= max_length else None

        reply_to = data.get("replyTo")
        request_id: UUID | None = None
        with suppress(ValueError):
            request_id = UUID(str(data.get("requestId")))
        context = data.get("clientContext")
        valid_context = (
            isinstance(context, dict)
            and len(context) <= _MAX_CONTEXT_PAIRS
            and all(isinstance(k, str) and isinstance(v, str) for k, v in context.items())
        )
        return cls(
            reply_to=reply_to if isinstance(reply_to, str) and _REPLY_TO.match(reply_to) else None,
            request_id=request_id,
            conversation_id=text("conversationId", 128),
            persona_id=text("personaId", 63),
            client_context=cast(dict[str, str], context) if valid_context else None,
        )


@dataclass
class Replier:
    """Publishes the replies of one request with consecutive `seq` numbers (plan 2.4)."""

    publisher: Publisher
    envelope: Envelope
    clock: Callable[[], datetime]
    seq: int = 0

    def _common(self, kind: str) -> dict[str, Any]:
        values = {
            "version": 1,
            "type": kind,
            "request_id": self.envelope.request_id,
            "conversation_id": self.envelope.conversation_id,
            "persona_id": self.envelope.persona_id,
            "seq": self.seq,
            "sent_at": self.clock(),
        }
        if self.envelope.client_context is not None:
            values["client_context"] = self.envelope.client_context
        return values

    async def _send(self, message: BaseModel) -> None:
        if self.envelope.reply_to is None:
            return
        await self.publisher.publish(
            self.envelope.reply_to, self.envelope.conversation_id, message, REPLY_SCHEMA
        )
        self.seq += 1

    async def accepted(self, deadline: datetime) -> None:
        await self._send(reply.AcceptedReply(**self._common("accepted"), deadline_at=deadline))

    async def token(self, text: str) -> None:
        await self._send(reply.TokenReply(**self._common("token"), text=text))

    async def final(self, message: reply.FinalReply) -> None:
        await self._send(message)

    def final_reply(self, **fields: Any) -> reply.FinalReply:
        return reply.FinalReply(**self._common("final"), **fields)

    async def error(self, code: ErrorCode, message: str) -> None:
        await self._send(
            reply.ErrorReply(
                **self._common("error"), code=code, message=message, retryable=RETRYABLE[code]
            )
        )


@dataclass
class TokenStreamer:
    """Groups the answer tokens and publishes them every TOKEN_FLUSH_SECONDS (D11).

    The last characters are held back until the end: if the canary starts to appear, it is
    never published, and once it appears nothing else is (the final reply replaces the text).
    """

    replier: Replier
    canary: str
    interval: float = TOKEN_FLUSH_SECONDS
    monotonic: Callable[[], float] = time.monotonic
    text: str = ""
    sent: int = 0
    leaked: bool = False
    first_token_at: float | None = None
    _last_flush: float = field(default=0.0)

    async def add(self, piece: str) -> None:
        if self.leaked or not piece:
            return
        self.text += piece
        if contains_canary(self.text, self.canary):
            self.leaked = True
            return
        if self.monotonic() - self._last_flush >= self.interval:
            await self._flush(len(self.text) - (len(self.canary) - 1))

    async def finish(self) -> None:
        if not self.leaked:
            await self._flush(len(self.text))

    async def _flush(self, end: int) -> None:
        self._last_flush = self.monotonic()
        if end <= self.sent:
            return
        if self.first_token_at is None:
            self.first_token_at = self._last_flush
        await self.replier.token(self.text[self.sent : end])
        self.sent = end


@dataclass(frozen=True)
class Outcome:
    """How a request ended, for the audit log."""

    outcome: str
    error_code: ErrorCode | None = None
    question: str | None = None
    answer: str | None = None
    state: AgentState | None = None
    flags: tuple[Flag, ...] = ()
    first_token_ms: int | None = None


class RequestProcessor:
    def __init__(
        self,
        *,
        graph: Graph,
        conversations: ConversationStore,
        processed: ProcessedRequests,
        rate_limiter: RateLimiter,
        audit_log: AuditLog,
        personas: PersonaDirectory,
        publisher: Publisher,
        messages: Messages,
        llm_model: str,
        max_question_chars: int,
        answer_timeout: timedelta,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._graph = graph
        self._conversations = conversations
        self._processed = processed
        self._rate_limiter = rate_limiter
        self._audit_log = audit_log
        self._personas = personas
        self._publisher = publisher
        self._messages = messages
        self._llm_model = llm_model
        self._max_question_chars = max_question_chars
        self._answer_timeout = answer_timeout
        self._clock = clock
        self._monotonic = monotonic
        self._locks: dict[tuple[str, str], tuple[asyncio.Lock, int]] = {}

    async def process(self, raw: bytes) -> None:
        """Handle one message of agent.requests. Never raises for a bad request."""
        started = self._monotonic()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict) and "version" in data and data["version"] != 1:
            await self._reject(Envelope.salvage(data), "UNSUPPORTED_VERSION", None, started)
            return
        try:
            request = AgentRequest.model_validate(data)
        except ValidationError:
            await self._reject(Envelope.salvage(data), "INVALID_REQUEST", None, started)
            return
        envelope = Envelope(
            reply_to=request.reply_to,
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            persona_id=request.persona_id,
            client_context=request.client_context,
        )
        async with self._conversation_lock(request.reply_to, request.conversation_id):
            try:
                await self._process_valid(request, envelope, started)
            except Exception:
                log.exception("request failed", extra={"request_id": str(request.request_id)})
                await self._reject(envelope, "INTERNAL_ERROR", request.question, started)

    async def _process_valid(
        self, request: AgentRequest, envelope: Envelope, started: float
    ) -> None:
        if await self._processed.contains(request.request_id):
            log.info("repeated request ignored", extra={"request_id": str(request.request_id)})
            return
        client_id = client_id_of(request.reply_to)
        now = self._clock()
        if not await self._rate_limiter.acquire(client_id, at=now):
            await self._reject(envelope, "RATE_LIMITED", request.question, started)
        elif len(request.question) > self._max_question_chars:
            await self._reject(envelope, "QUESTION_TOO_LONG", request.question, started)
        elif (persona := await self._personas.get_persona(request.persona_id)) is None:
            await self._reject(envelope, "PERSONA_NOT_FOUND", request.question, started)
        else:
            await self._answer(request, envelope, persona, client_id, now, started)
        await self._processed.add(request.request_id, client_id, at=now)

    async def _answer(
        self,
        request: AgentRequest,
        envelope: Envelope,
        persona: Persona,
        client_id: str,
        now: datetime,
        started: float,
    ) -> None:
        thread = await self._conversations.resolve(
            client_id, request.conversation_id, persona.id, at=now
        )
        replier = Replier(self._publisher, envelope, self._clock)
        await replier.accepted(now + self._answer_timeout)
        canary = new_canary()
        streamer = TokenStreamer(replier, canary, monotonic=self._monotonic)
        ref = PersonaRef(id=persona.id, display_name=persona.display_name)
        config: RunnableConfig = {"configurable": {"thread_id": thread.thread_id}}
        state: AgentState | None = None
        error: ErrorCode | None = None
        try:
            async with asyncio.timeout(self._answer_timeout.total_seconds()):
                async for mode, payload in self._graph.astream(
                    turn_input(request.question, ref, canary),
                    config,
                    stream_mode=["messages", "values"],
                ):
                    if mode == "values":
                        state = cast(AgentState, payload)
                        continue
                    chunk, metadata = cast(tuple[BaseMessage, dict[str, Any]], payload)
                    if ANSWER_STREAM_TAG in metadata.get("tags", []):
                        await streamer.add(chunk.text)
        except TimeoutError:
            error = "TIMEOUT"
        except Exception as failure:
            if is_llm_unavailable(failure):
                log.warning("LLM unavailable", exc_info=True)
                error = "LLM_UNAVAILABLE"
            else:
                log.exception("graph failed", extra={"request_id": str(request.request_id)})
                error = "INTERNAL_ERROR"

        if error is not None or state is None or "outcome" not in state:
            code: ErrorCode = error or "INTERNAL_ERROR"
            first_token_ms = self._first_token_ms(started, streamer)
            await replier.error(code, self._messages.error(code))
            await self._audit(
                envelope,
                Outcome("error", code, request.question, first_token_ms=first_token_ms),
                started,
            )
            return

        await streamer.finish()
        first_token_ms = self._first_token_ms(started, streamer)
        total_ms = self._elapsed_ms(started, self._monotonic())
        referral = state.get("referral")
        await replier.final(
            replier.final_reply(
                answer=state["answer"],
                outcome=state["outcome"],
                persona=reply.PersonaRef(id=persona.id, display_name=persona.display_name),
                citations=[reply.Citation(**_citation(c)) for c in state.get("citations", [])],
                referral=None
                if referral is None
                else reply.PersonaRef(
                    id=referral["persona_id"], display_name=referral["display_name"]
                ),
                timing=reply.Timing(first_token_ms=first_token_ms, total_ms=total_ms),
            )
        )
        await self._audit(
            envelope,
            Outcome(
                state["outcome"],
                None,
                request.question,
                state["answer"],
                state,
                tuple(state.get("flags", [])),
                first_token_ms,
            ),
            started,
        )

    async def _reject(
        self, envelope: Envelope, code: ErrorCode, question: str | None, started: float
    ) -> None:
        """An error before (or instead of) running the graph. Unreadable requests without a
        valid replyTo get no reply, but are audited (plan 2.4)."""
        if envelope.reply_to is None:
            log.warning("request without a valid replyTo dropped", extra={"code": code})
        replier = Replier(self._publisher, envelope, self._clock)
        await replier.error(code, self._messages.error(code))
        flag = _FLAGS.get(code)
        await self._audit(
            envelope,
            Outcome("error", code, question, flags=() if flag is None else (flag,)),
            started,
        )

    async def _audit(self, envelope: Envelope, result: Outcome, started: float) -> None:
        state = result.state or {}
        referral = state.get("referral")
        entry = audit.AuditEntry(
            version=1,
            audit_id=uuid4(),
            request_id=envelope.request_id,
            client_id=envelope.client_id,
            conversation_id=envelope.conversation_id,
            persona_id=envelope.persona_id,
            question=result.question,
            answer=result.answer,
            outcome=cast(Any, result.outcome),
            error_code=result.error_code,
            citations=[audit.Citation(**_citation(c)) for c in state.get("citations", [])],
            referral_persona_id=None if referral is None else referral["persona_id"],
            flags=list(result.flags),
            llm_model=self._llm_model,
            prompt_version=PROMPT_VERSION,
            first_token_ms=result.first_token_ms,
            total_ms=self._elapsed_ms(started, self._monotonic()),
            created_at=self._clock(),
        )
        await self._audit_log.record(entry)
        key = str(envelope.request_id or entry.audit_id)
        await self._publisher.publish(AUDIT_TOPIC, key, entry, AUDIT_SCHEMA)

    def _first_token_ms(self, started: float, streamer: TokenStreamer) -> int | None:
        at = streamer.first_token_at
        return None if at is None else self._elapsed_ms(started, at)

    @staticmethod
    def _elapsed_ms(start: float, end: float) -> int:
        return max(0, round((end - start) * 1000))

    @asynccontextmanager
    async def _conversation_lock(self, reply_to: str, conversation_id: str) -> AsyncIterator[None]:
        """One request at a time per conversation, in arrival order (asyncio.Lock is FIFO)."""
        key = (reply_to, conversation_id)
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)


def _citation(citation: Any) -> dict[str, Any]:
    url = citation["url"]
    try:
        parsed = None if url is None else AnyUrl(url)
    except ValidationError:
        parsed = None
    return {
        "document_id": citation["document_id"],
        "title": citation["title"],
        "url": parsed,
        "path": citation["path"],
        "section": citation["section"],
        "source_type": citation["source_type"],
    }
