"""Ingestion Worker (`flock-ingest worker`, plan 5.1, D31).

Consumes ingestion.jobs and runs each job with the ingestion pipeline, publishing its progress and
result to ingestion.events. Jobs run as concurrent tasks on purpose: while one update runs, the
next job fails to take the ingestion lock and is answered with `rejected` (spec HU4.9), instead of
waiting for its turn.

Offsets are committed once a job is handled, in order per partition (common.kafka.OffsetTracker).
A job delivered again after it was handled (the worker died before committing) is skipped.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiokafka import AIOKafkaConsumer, TopicPartition
from pydantic import ValidationError

from flock_agent.common.kafka import OffsetTracker
from flock_agent.contracts.generated.ingestion_job_v1 import IngestionJob
from flock_agent.ingestion.pipeline import IngestionPipeline
from flock_agent.knowledge.repository import KnowledgeRepository

log = logging.getLogger(__name__)

JOBS_TOPIC = "ingestion.jobs"
EVENTS_TOPIC = "ingestion.events"
EVENT_SCHEMA = "ingestion-event.v1"
CONSUMER_GROUP = (
    "ingestion"  # the ACLs only let the ingestion use this group (infra/kafka/setup.sh)
)
KAFKA_CLIENT_ID = "ingestion"
_POLL_TIMEOUT_MS = 500
# Jobs handled at the same time: one runs, the others are rejected right away.
_MAX_CONCURRENT_JOBS = 4


class JobHandler:
    """Runs one job with the pipeline. Never raises: a failed update is reported by its events."""

    def __init__(self, pipeline: IngestionPipeline, repository: KnowledgeRepository) -> None:
        self._pipeline = pipeline
        self._repository = repository

    async def handle(self, raw: bytes) -> None:
        try:
            job = IngestionJob.model_validate_json(raw)
        except ValidationError as error:
            log.error("unreadable ingestion job skipped", extra={"error": str(error)})
            return
        if await self._repository.get_run(job.job_id) is not None:
            log.info("ingestion job already handled", extra={"job_id": str(job.job_id)})
            return
        if job.sources:
            # TODO(T49): external sources arrive in stage 3; only the folders are read for now.
            log.warning(
                "external sources not supported yet: only the folders are updated",
                extra={"job_id": str(job.job_id), "sources": len(job.sources)},
            )
        with contextlib.suppress(Exception):  # the pipeline already logged it and sent `failed`
            await self._pipeline.run(job.job_id, job.trigger)


class IngestionWorker:
    def __init__(
        self,
        consumer: AIOKafkaConsumer,
        handle: Callable[[bytes], Awaitable[None]],
        *,
        max_concurrent: int = _MAX_CONCURRENT_JOBS,
        heartbeat: Path | None = None,
    ) -> None:
        self._consumer = consumer
        self._handle_job = handle
        self._slots = asyncio.Semaphore(max_concurrent)
        self._offsets = OffsetTracker()
        self._tasks: set[asyncio.Task[None]] = set()
        self._heartbeat = heartbeat

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                batch = await self._consumer.getmany(timeout_ms=_POLL_TIMEOUT_MS)
                for partition, records in batch.items():
                    for record in records:
                        await self._slots.acquire()
                        self._offsets.start(partition, record.offset)
                        task = asyncio.create_task(
                            self._handle(partition, record.offset, record.value)
                        )
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                await self._commit()
                if self._heartbeat is not None:
                    self._heartbeat.touch()
        finally:
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            await self._commit()

    async def _handle(self, partition: TopicPartition, offset: int, value: bytes | None) -> None:
        try:
            await self._handle_job(value or b"")
        except Exception:
            log.exception("ingestion job handling failed", extra={"offset": offset})
        finally:
            self._offsets.finish(partition, offset)
            self._slots.release()

    async def _commit(self) -> None:
        if commits := self._offsets.committable():
            await self._consumer.commit(commits)
