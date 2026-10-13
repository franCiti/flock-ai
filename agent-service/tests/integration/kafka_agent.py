"""An Agent Worker over an ephemeral Kafka, for the integration tests (T25, T26).

Each test gets its own topics and consumer group, so tests never see each other's messages.
"""

import asyncio
import json
import uuid
from datetime import timedelta
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from langgraph.checkpoint.memory import InMemorySaver

from flock_agent.agent.audit import AuditLog
from flock_agent.agent.conversations import ConversationStore
from flock_agent.agent.graph.builder import build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.idempotency import ProcessedRequests
from flock_agent.agent.messages import Messages
from flock_agent.agent.processing import AUDIT_TOPIC, RequestProcessor
from flock_agent.agent.rate_limit import RateLimiter
from flock_agent.agent.worker import AgentWorker
from flock_agent.common.db import Pool
from flock_agent.common.kafka import KafkaPublisher
from flock_agent.knowledge.repository import KnowledgeRepository

REQUEST_PARTITIONS = 3


class Topics:
    """Unique names for one test: a request topic, two reply topics and a consumer group."""

    def __init__(self) -> None:
        suffix = uuid.uuid4().hex[:8]
        self.requests = f"agent.requests.{suffix}"
        self.app_a = f"agent.replies.a-{suffix}"
        self.app_b = f"agent.replies.b-{suffix}"
        self.group = f"agent-{suffix}"

    async def create(self, kafka: str) -> "Topics":
        admin = AIOKafkaAdminClient(bootstrap_servers=kafka)
        await admin.start()
        try:
            await admin.create_topics(
                [
                    NewTopic(self.requests, REQUEST_PARTITIONS, 1),
                    NewTopic(self.app_a, 1, 1),
                    NewTopic(self.app_b, 1, 1),
                ]
            )
            if AUDIT_TOPIC not in await admin.list_topics():
                await admin.create_topics([NewTopic(AUDIT_TOPIC, 1, 1)])
        finally:
            await admin.close()
        return self


class RunningWorker:
    """The worker consuming the test's request topic, with the given graph dependencies."""

    def __init__(self, kafka: str, topics: Topics, pool: Pool, deps: Dependencies) -> None:
        self.kafka, self.topics, self.pool, self.deps = kafka, topics, pool, deps
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
        processor = RequestProcessor(
            graph=build_graph(self.deps, InMemorySaver(serde=checkpoint_serializer())),
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
            for partition in range(REQUEST_PARTITIONS)
        ]
        return sum(offsets)
