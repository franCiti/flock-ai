"""The Agent Worker over real Kafka (task T25, plan 4.1): requests in, replies out, offsets."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer

from flock_agent.agent.fake_llm import FakeChatModel
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.messages import Messages
from flock_agent.agent.processing import AUDIT_TOPIC
from flock_agent.common.db import Pool
from flock_agent.knowledge.models import Persona
from flock_agent.knowledge.repository import KnowledgeRepository
from tests.fakes import FakeSearch
from tests.integration.containers import running_kafka
from tests.integration.kafka_agent import RunningWorker, Topics

pytestmark = pytest.mark.integration_containers


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    with running_kafka() as bootstrap:
        yield bootstrap


@pytest.fixture
async def topics(kafka: str) -> Topics:
    return await Topics().create(kafka)


@pytest.fixture
async def pool(knowledge: KnowledgeRepository, agent_tables: Pool) -> Pool:
    await knowledge.upsert_persona(
        Persona(id="juan-plataforma", display_name="Juan Pérez", profile_hash="h")
    )
    return agent_tables


def deps(fast: FakeChatModel) -> Dependencies:
    return Dependencies(
        main_model=FakeChatModel.scripted([]),
        fast_model=fast,
        search=FakeSearch(),
        messages=Messages(),
        history_turns=6,
    )


def request(question: str, reply_to: str, conversation: str = "c1") -> dict[str, Any]:
    return {
        "version": 1,
        "requestId": str(uuid.uuid4()),
        "conversationId": conversation,
        "personaId": "juan-plataforma",
        "question": question,
        "replyTo": reply_to,
        "sentAt": "2026-10-13T15:00:00Z",
    }


def classification(intent: str) -> dict[str, Any]:
    return {
        "language": "es",
        "intent": intent,
        "standalone_query": "¿Cómo hago rollback?",
        "manipulation_attempt": False,
    }


async def read_until_terminal(kafka: str, topic: str, expected: int) -> list[dict[str, Any]]:
    """Messages of a reply topic until `expected` requests got their final or error."""
    consumer = AIOKafkaConsumer(topic, bootstrap_servers=kafka, auto_offset_reset="earliest")
    await consumer.start()
    messages: list[dict[str, Any]] = []
    try:
        async with asyncio.timeout(60):
            while sum(m["type"] in ("final", "error") for m in messages) < expected:
                batch = await consumer.getmany(timeout_ms=500)
                for records in batch.values():
                    messages.extend(json.loads(record.value) for record in records)
    finally:
        await consumer.stop()
    return messages


async def read_until_audit(kafka: str, request_id: str) -> dict[str, Any]:
    consumer = AIOKafkaConsumer(AUDIT_TOPIC, bootstrap_servers=kafka, auto_offset_reset="earliest")
    await consumer.start()
    try:
        async with asyncio.timeout(30):
            while True:
                batch = await consumer.getmany(timeout_ms=500)
                for records in batch.values():
                    for record in records:
                        entry: dict[str, Any] = json.loads(record.value)
                        if entry["requestId"] == request_id:
                            return entry
    finally:
        await consumer.stop()


async def test_a_request_and_its_replies_over_kafka(kafka: str, topics: Topics, pool: Pool) -> None:
    fast = FakeChatModel.scripted([classification("question"), {"verdict": "none"}])
    async with RunningWorker(kafka, topics, pool, deps(fast)) as worker:
        values = request("¿Cómo hago rollback?", topics.app_a)
        await worker.send(values)
        replies = await read_until_terminal(kafka, topics.app_a, 1)

    assert [r["type"] for r in replies] == ["accepted", "final"]
    assert [r["seq"] for r in replies] == [0, 1]
    assert replies[-1]["requestId"] == values["requestId"]
    assert replies[-1]["outcome"] == "no_information"
    # The offset of the handled request was committed.
    assert worker.committed_at_exit == 1
    audit = await read_until_audit(kafka, values["requestId"])
    assert audit["outcome"] == "no_information"


async def test_two_apps_get_only_their_replies(kafka: str, topics: Topics, pool: Pool) -> None:
    fast = FakeChatModel.scripted([classification("small_talk"), classification("small_talk")])
    async with RunningWorker(kafka, topics, pool, deps(fast)) as worker:
        first = request("Hola", topics.app_a)
        second = request("Hola", topics.app_b)
        await asyncio.gather(worker.send(first), worker.send(second))
        replies_a = await read_until_terminal(kafka, topics.app_a, 1)
        replies_b = await read_until_terminal(kafka, topics.app_b, 1)

    assert {r["requestId"] for r in replies_a} == {first["requestId"]}
    assert {r["requestId"] for r in replies_b} == {second["requestId"]}
    assert [r["type"] for r in replies_a] == ["accepted", "final"]
    assert [r["type"] for r in replies_b] == ["accepted", "final"]
