"""The Ingestion Worker over real Kafka (task T34, plan 5.1, D31): jobs in, events out."""

import asyncio
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from flock_agent.common.kafka import KafkaPublisher
from flock_agent.ingestion.pipeline import AnyEvent, IngestionPipeline
from flock_agent.ingestion.worker import EVENT_SCHEMA, IngestionWorker, JobHandler
from flock_agent.knowledge.repository import KnowledgeRepository
from tests.fakes import FakeEmbedder
from tests.integration.containers import running_kafka

pytestmark = pytest.mark.integration_containers

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    with running_kafka() as bootstrap:
        yield bootstrap


class Ingestion:
    """The worker consuming a jobs topic of its own and publishing to an events topic of its own."""

    def __init__(self, kafka: str, knowledge: KnowledgeRepository, root: Path) -> None:
        suffix = uuid.uuid4().hex[:8]
        self.kafka, self.knowledge, self.root = kafka, knowledge, root
        self.jobs, self.events, self.group = f"jobs-{suffix}", f"events-{suffix}", f"ing-{suffix}"
        self.stop = asyncio.Event()

    async def __aenter__(self) -> "Ingestion":
        admin = AIOKafkaAdminClient(bootstrap_servers=self.kafka)
        await admin.start()
        try:
            await admin.create_topics([NewTopic(self.jobs, 1, 1), NewTopic(self.events, 1, 1)])
        finally:
            await admin.close()
        self.producer = AIOKafkaProducer(bootstrap_servers=self.kafka, acks="all")
        await self.producer.start()
        publisher = KafkaPublisher(self.producer)

        async def publish(event: AnyEvent) -> None:
            await publisher.publish(self.events, str(event.job_id), event, EVENT_SCHEMA)

        pipeline = IngestionPipeline(
            self.knowledge,
            FakeEmbedder(),
            knowledge_root=self.root,
            max_bytes=20 * 1024 * 1024,
            on_event=publish,
        )
        self.consumer = AIOKafkaConsumer(
            self.jobs,
            bootstrap_servers=self.kafka,
            group_id=self.group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self.consumer.start()
        worker = IngestionWorker(self.consumer, JobHandler(pipeline, self.knowledge).handle)
        self.task = asyncio.create_task(worker.run(self.stop))
        return self

    async def __aexit__(self, *_: object) -> None:
        self.stop.set()
        await self.task
        self.committed = await self.consumer.committed(TopicPartition(self.jobs, 0)) or 0
        await self.consumer.stop()
        await self.producer.stop()

    async def send_job(
        self, job_id: uuid.UUID | None = None, raw: bytes | None = None
    ) -> uuid.UUID:
        job_id = job_id or uuid.uuid4()
        value = (
            raw
            or json.dumps(
                {
                    "version": 1,
                    "jobId": str(job_id),
                    "trigger": "manual",
                    "requestedAt": "2026-10-15T12:00:00Z",
                    "sources": [],
                }
            ).encode()
        )
        await self.producer.send_and_wait(self.jobs, value, key=str(job_id).encode())
        return job_id

    async def events_until(self, terminal_jobs: int) -> list[dict[str, Any]]:
        """Events of the topic until `terminal_jobs` jobs reached completed, failed or rejected."""
        consumer = AIOKafkaConsumer(
            self.events, bootstrap_servers=self.kafka, auto_offset_reset="earliest"
        )
        await consumer.start()
        events: list[dict[str, Any]] = []
        try:
            async with asyncio.timeout(120):
                while (
                    sum(e["type"] in ("completed", "failed", "rejected") for e in events)
                    < terminal_jobs
                ):
                    batch = await consumer.getmany(timeout_ms=500)
                    for records in batch.values():
                        events.extend(json.loads(record.value) for record in records)
        finally:
            await consumer.stop()
        return events


@pytest.fixture
def root(tmp_path: Path) -> Path:
    destination = tmp_path / "knowledge"
    shutil.copytree(EXAMPLES, destination)
    return destination


async def test_a_job_is_run_and_its_events_published(
    kafka: str, knowledge: KnowledgeRepository, root: Path
) -> None:
    async with Ingestion(kafka, knowledge, root) as ingestion:
        job = await ingestion.send_job()
        events = await ingestion.events_until(1)

    assert [e["type"] for e in events] == [
        "started",
        "persona_completed",
        "persona_completed",
        "completed",
    ]
    assert {e["jobId"] for e in events} == {str(job)}
    assert {e["summary"]["personaId"] for e in events if e["type"] == "persona_completed"} == {
        "ana-datos",
        "juan-plataforma",
    }
    run = await knowledge.get_run(job)
    assert run is not None
    assert run.status == "completed"
    assert ingestion.committed == 1


async def test_a_second_job_while_one_runs_is_rejected(
    kafka: str, knowledge: KnowledgeRepository, root: Path
) -> None:
    async with Ingestion(kafka, knowledge, root) as ingestion:
        first = await ingestion.send_job()
        second = await ingestion.send_job()
        events = await ingestion.events_until(2)

    terminal = {e["jobId"]: e for e in events if e["type"] in ("completed", "rejected")}
    assert {terminal[str(first)]["type"], terminal[str(second)]["type"]} == {
        "completed",
        "rejected",
    }
    rejected = next(e for e in terminal.values() if e["type"] == "rejected")
    assert rejected["reason"] == "another update is already running"
    assert ingestion.committed == 2


async def test_a_repeated_or_unreadable_job_is_skipped(
    kafka: str, knowledge: KnowledgeRepository, root: Path
) -> None:
    async with Ingestion(kafka, knowledge, root) as ingestion:
        job = await ingestion.send_job()
        await ingestion.events_until(1)
        await ingestion.send_job(job)  # delivered again
        await ingestion.send_job(raw=b"{not json")
        other = await ingestion.send_job()
        events = await ingestion.events_until(2)

    started = [e["jobId"] for e in events if e["type"] == "started"]
    assert started == [str(job), str(other)]
    assert ingestion.committed == 4
