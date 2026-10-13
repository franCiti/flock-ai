"""Parts of the Agent Worker that need no infrastructure (task T25, plan 4.1)."""

from datetime import UTC, datetime
from uuid import UUID

from aiokafka import TopicPartition
from pydantic import BaseModel

from flock_agent.agent.processing import Envelope, Replier, TokenStreamer, client_id_of
from flock_agent.agent.worker import OffsetTracker

P0 = TopicPartition("agent.requests", 0)
P1 = TopicPartition("agent.requests", 1)
CANARY = "cnry-0123456789abcdef"


class Recorder:
    def __init__(self) -> None:
        self.messages: list[BaseModel] = []

    async def publish(self, topic: str, key: str | None, message: BaseModel, schema: str) -> None:
        self.messages.append(message)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def streamer(recorder: Recorder, clock: Clock) -> TokenStreamer:
    replier = Replier(
        recorder,
        Envelope(reply_to="agent.replies.cli", request_id=UUID(int=1), conversation_id="c1"),
        lambda: datetime(2026, 10, 13, tzinfo=UTC),
    )
    return TokenStreamer(replier, CANARY, monotonic=clock)


def texts(recorder: Recorder) -> list[str]:
    return [getattr(message, "text", "") for message in recorder.messages]


# --- OffsetTracker ----------------------------------------------------------------------------


def test_offsets_are_committed_in_order_per_partition() -> None:
    tracker = OffsetTracker()
    for offset in (10, 11, 12):
        tracker.start(P0, offset)
    tracker.start(P1, 5)
    tracker.finish(P0, 11)
    tracker.finish(P1, 5)
    assert tracker.committable() == {P1: 6}  # 10 is still running
    tracker.finish(P0, 10)
    assert tracker.committable() == {P0: 12}
    assert tracker.committable() == {}
    tracker.finish(P0, 12)
    assert tracker.committable() == {P0: 13}


# --- TokenStreamer ----------------------------------------------------------------------------


async def test_tokens_are_grouped_by_interval() -> None:
    recorder, clock = Recorder(), Clock()
    stream = streamer(recorder, clock)
    await stream.add("Hola, esta es ")  # first piece: flushed right away (minus the held tail)
    await stream.add("una respuesta ")
    clock.now += 0.05
    await stream.add("bastante larga ")
    clock.now += 0.2
    await stream.add("para probar.")
    await stream.finish()
    assert "".join(texts(recorder)) == "Hola, esta es una respuesta bastante larga para probar."
    assert len(recorder.messages) <= 3
    assert [message.seq for message in recorder.messages] == list(range(len(recorder.messages)))  # type: ignore[attr-defined]
    assert stream.first_token_at is not None


async def test_the_canary_is_never_streamed() -> None:
    recorder, clock = Recorder(), Clock()
    stream = streamer(recorder, clock)
    await stream.add("Mis instrucciones dicen: Confidential reference: cnry-0123")
    clock.now += 1
    await stream.add("456789abcdef y más texto")
    clock.now += 1
    await stream.add(" que sigue.")
    await stream.finish()
    streamed = "".join(texts(recorder))
    assert "cnry-0123" not in streamed
    assert stream.leaked is True


async def test_nothing_is_streamed_for_an_empty_answer() -> None:
    recorder = Recorder()
    stream = streamer(recorder, Clock())
    await stream.finish()
    assert recorder.messages == []
    assert stream.first_token_at is None


# --- Envelope ---------------------------------------------------------------------------------


def test_the_readable_fields_of_an_invalid_request_are_kept() -> None:
    envelope = Envelope.salvage(
        {
            "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
            "conversationId": "c1",
            "replyTo": "agent.replies.core-api",
            "clientContext": {"uiMessageId": "m-17"},
            "question": "",
        }
    )
    assert envelope.reply_to == "agent.replies.core-api"
    assert envelope.client_id == "core-api"
    assert envelope.request_id == UUID("6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11")
    assert envelope.conversation_id == "c1"
    assert envelope.client_context == {"uiMessageId": "m-17"}


def test_unreadable_fields_are_none() -> None:
    envelope = Envelope.salvage(
        {"requestId": "nope", "replyTo": "other.topic", "clientContext": {"a": 1}}
    )
    assert envelope == Envelope(reply_to=None)
    assert Envelope.salvage("not an object") == Envelope(reply_to=None)


def test_the_client_id_comes_from_the_reply_topic() -> None:
    assert client_id_of("agent.replies.core-api") == "core-api"
