"""The Agent Worker over real Kafka (task T25, plan 4.1): requests in, replies out, offsets.

Each test uses its own topics and consumer group, so tests never see each other's messages.
"""

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from langgraph.checkpoint.memory import InMemorySaver

from flock_agent.agent.audit import AuditLog
from flock_agent.agent.conversations import ConversationStore
from flock_agent.agent.fake_llm import FakeChatModel
from flock_agent.agent.graph.builder import build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.idempotency import ProcessedRequests
from flock_agent.agent.messages import Messages
from flock_agent.agent.processing import AUDIT_TOPIC, RequestProcessor
from flock_agent.agent.rate_limit import RateLimiter
from flock_agent.agent.worker import AgentWorker
from flock_agent.common.db import Pool
from flock_agent.common.kafka import KafkaPublisher
from flock_agent.knowledge.models import Persona
from flock_agent.knowledge.repository import KnowledgeRepository
from tests.fakes import FakeSearch
from tests.integration.containers import running_kafka

pytestmark = pytest.mark.integration_containers

ANSWER = "Ejecutá el job rollback-prod [1]."


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    with running_kafka() as bootstrap:
        yield bootstrap


class Topics:
    def __init__(self) -> None:
        suffix = uuid.uuid4().hex[:8]
        self.requests = f"agent.requests.{suffix}"
        self.app_a = f"agent.replies.a-{suffix}"
        self.app_b = f"agent.replies.b-{suffix}"
        self.group = f"agent-{suffix}"


@pytest.fixture
async def topics(kafka: str) -> Topics:
    names = Topics()
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka)
    await admin.start()
    try:
        await admin.create_topics(
            [
                NewTopic(names.requests, num_partitions=3, replication_factor=1),
                NewTopic(names.app_a, num_partitions=1, replication_factor=1),
                NewTopic(names.app_b, num_partitions=1, replication_factor=1),
            ]
        )
        existing = await admin.list_topics()
        if AUDIT_TOPIC not in existing:
            await admin.create_topics([NewTopic(AUDIT_TOPIC, 1, 1)])
    finally:
        await admin.close()
    return names


@pytest.fixture
async def pool(knowledge: KnowledgeRepository, agent_tables: Pool) -> Pool:
    await knowledge.upsert_persona(
        Persona(id="juan-plataforma", display_name="Juan Pérez", profile_hash="h")
    )
    return agent_tables


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


class RunningWorker:
    """The worker consuming the test's request topic, with fake models."""

    def __init__(self, kafka: str, topics: Topics, pool: Pool, fast: FakeChatModel) -> None:
        self.kafka, self.topics, self.pool, self.fast = kafka, topics, pool, fast
        self.stop = asyncio.Event()
        self.committed_at_exit = 0

    async def __aenter__(self) -> "RunningWorker":
        self.producer = AIOKafkaProducer(bootstrap_servers=self.kafka, acks="all")
        await self.producer.start()
        self.consumer = AIOKafkaConsumer(
            self.topics.requests,
            bootstrap_servers=self.kafka,
            group_id=self.topics.group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self.consumer.start()
        deps = Dependencies(
            main_model=FakeChatModel.scripted([ANSWER]),
            fast_model=self.fast,
            search=FakeSearch(),
            messages=Messages(),
            history_turns=6,
        )
        processor = RequestProcessor(
            graph=build_graph(deps, InMemorySaver(serde=checkpoint_serializer())),
            conversations=ConversationStore(self.pool, timedelta(days=1)),
            processed=ProcessedRequests(self.pool),
            rate_limiter=RateLimiter(self.pool, 30),
            audit_log=AuditLog(self.pool),
            personas=KnowledgeRepository(self.pool),
            publisher=KafkaPublisher(self.producer),
            messages=Messages(),
            llm_model="fake-model",
            max_question_chars=2000,
            answer_timeout=timedelta(seconds=30),
        )
        worker = AgentWorker(self.consumer, processor.process, max_concurrent=4)
        self.task = asyncio.create_task(worker.run(self.stop))
        return self

    async def __aexit__(self, *_: object) -> None:
        self.stop.set()
        await self.task
        self.committed_at_exit = await self.committed()
        await self.consumer.stop()
        await self.producer.stop()

    async def send(self, values: dict[str, Any]) -> None:
        await self.producer.send_and_wait(
            self.topics.requests,
            json.dumps(values).encode(),
            key=values["conversationId"].encode(),
        )

    async def committed(self) -> int:
        offsets = [
            await self.consumer.committed(TopicPartition(self.topics.requests, partition)) or 0
            for partition in range(3)
        ]
        return sum(offsets)


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


async def test_a_request_and_its_replies_over_kafka(kafka: str, topics: Topics, pool: Pool) -> None:
    fast = FakeChatModel.scripted([classification("question"), {"verdict": "none"}])
    async with RunningWorker(kafka, topics, pool, fast) as worker:
        values = request("¿Cómo hago rollback?", topics.app_a)
        await worker.send(values)
        replies = await read_until_terminal(kafka, topics.app_a, 1)

    assert [r["type"] for r in replies] == ["accepted", "final"]
    assert [r["seq"] for r in replies] == [0, 1]
    # The offset of the handled request was committed.
    assert worker.committed_at_exit == 1
    assert replies[-1]["requestId"] == values["requestId"]
    assert replies[-1]["outcome"] == "no_information"
    audit = await read_until_audit(kafka, values["requestId"])
    assert audit["outcome"] == "no_information"


async def test_two_apps_get_only_their_replies(kafka: str, topics: Topics, pool: Pool) -> None:
    fast = FakeChatModel.scripted([classification("small_talk"), classification("small_talk")])
    async with RunningWorker(kafka, topics, pool, fast) as worker:
        first = request("Hola", topics.app_a)
        second = request("Hola", topics.app_b)
        await asyncio.gather(worker.send(first), worker.send(second))
        replies_a = await read_until_terminal(kafka, topics.app_a, 1)
        replies_b = await read_until_terminal(kafka, topics.app_b, 1)

    assert {r["requestId"] for r in replies_a} == {first["requestId"]}
    assert {r["requestId"] for r in replies_b} == {second["requestId"]}
    assert [r["type"] for r in replies_a] == ["accepted", "final"]
    assert [r["type"] for r in replies_b] == ["accepted", "final"]


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
