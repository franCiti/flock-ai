"""Agent Worker (`flock-agent`, plan 4.1).

Consumes agent.requests and answers each request on its replyTo topic. Several requests run at
the same time (MAX_CONCURRENT_REQUESTS); the ones of a conversation, one at a time and in order
(see processing.RequestProcessor).

Delivery is "at least once": the offset of a message is committed only after its request has
been handled, and in order per partition. If the worker dies halfway, the pending requests are
consumed again; the idempotency check skips the ones already answered.
"""

import asyncio
import contextlib
import logging
import signal
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiokafka import AIOKafkaConsumer, TopicPartition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from flock_agent.agent.audit import AuditLog
from flock_agent.agent.conversations import ConversationStore
from flock_agent.agent.graph.builder import build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.idempotency import ProcessedRequests
from flock_agent.agent.llm import create_models
from flock_agent.agent.messages import load_messages
from flock_agent.agent.processing import RequestProcessor
from flock_agent.agent.rate_limit import RateLimiter
from flock_agent.common.aio import run_async
from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.db import conninfo, open_pool
from flock_agent.common.kafka import KafkaPublisher, start_consumer, start_producer
from flock_agent.common.migrations import apply_migrations
from flock_agent.common.settings import Settings
from flock_agent.knowledge.embeddings import FastEmbedEmbedder
from flock_agent.knowledge.repository import META_EMBEDDING_MODEL, KnowledgeRepository
from flock_agent.knowledge.search import KnowledgeSearch

log = logging.getLogger(__name__)

REQUESTS_TOPIC = "agent.requests"
CONSUMER_GROUP = "agent"  # the ACLs only let the agent use this group (infra/kafka/setup.sh)
KAFKA_CLIENT_ID = "agent"
MAINTENANCE_INTERVAL = timedelta(minutes=10)
_POLL_TIMEOUT_MS = 500


class OffsetTracker:
    """Which offsets can be committed: those below the oldest request still running.

    Requests finish in any order, but a partition's offset can only move past a message once
    every earlier message of that partition is done.
    """

    def __init__(self) -> None:
        self._pending: dict[TopicPartition, deque[int]] = {}
        self._done: dict[TopicPartition, set[int]] = {}
        self._committed: dict[TopicPartition, int] = {}

    def start(self, partition: TopicPartition, offset: int) -> None:
        self._pending.setdefault(partition, deque()).append(offset)

    def finish(self, partition: TopicPartition, offset: int) -> None:
        self._done.setdefault(partition, set()).add(offset)

    def committable(self) -> dict[TopicPartition, int]:
        """New offsets to commit (the next offset to read of each partition)."""
        commits: dict[TopicPartition, int] = {}
        for partition, pending in self._pending.items():
            done = self._done.get(partition, set())
            last = None
            while pending and pending[0] in done:
                last = pending.popleft()
                done.discard(last)
            if last is not None and self._committed.get(partition) != last + 1:
                commits[partition] = self._committed[partition] = last + 1
        return commits


class AgentWorker:
    def __init__(
        self,
        consumer: AIOKafkaConsumer,
        process: Callable[[bytes], Awaitable[None]],
        *,
        max_concurrent: int,
        maintenance: Callable[[], Awaitable[None]] | None = None,
        maintenance_interval: timedelta = MAINTENANCE_INTERVAL,
        heartbeat: Path | None = None,
    ) -> None:
        self._consumer = consumer
        self._process = process
        self._slots = asyncio.Semaphore(max_concurrent)
        self._offsets = OffsetTracker()
        self._tasks: set[asyncio.Task[None]] = set()
        self._maintenance = maintenance
        self._maintenance_interval = maintenance_interval
        self._heartbeat = heartbeat

    async def run(self, stop: asyncio.Event) -> None:
        maintenance = None
        if self._maintenance is not None:
            maintenance = asyncio.create_task(self._maintain(self._maintenance, stop))
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
                self._beat()
        finally:
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            await self._commit()
            if maintenance is not None:
                maintenance.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await maintenance

    def _beat(self) -> None:
        """Show the loop is alive (the container health check looks at the file's age)."""
        if self._heartbeat is not None:
            self._heartbeat.touch()

    async def _handle(self, partition: TopicPartition, offset: int, value: bytes | None) -> None:
        try:
            await self._process(value or b"")
        except Exception:
            # The processor answers every request it can; this is a bug or the broker is down.
            log.exception("request handling failed", extra={"offset": offset})
        finally:
            self._offsets.finish(partition, offset)
            self._slots.release()

    async def _commit(self) -> None:
        if commits := self._offsets.committable():
            await self._consumer.commit(commits)

    async def _maintain(self, task: Callable[[], Awaitable[None]], stop: asyncio.Event) -> None:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._maintenance_interval.total_seconds())
            if stop.is_set():
                return
            try:
                await task()
            except Exception:
                log.exception("maintenance failed")


def maintenance_task(
    conversations: ConversationStore,
    processed: ProcessedRequests,
    rate_limiter: RateLimiter,
    checkpointer: AsyncPostgresSaver,
) -> Callable[[], Awaitable[None]]:
    """Forget expired conversations (and their checkpoints), old request ids and old windows."""

    async def delete_threads(thread_ids: Sequence[str]) -> None:
        for thread_id in thread_ids:
            await checkpointer.adelete_thread(thread_id)

    async def run() -> None:
        now = datetime.now(UTC)
        removed = await conversations.purge_expired(delete_threads, at=now)
        requests = await processed.purge(at=now)
        windows = await rate_limiter.purge(at=now)
        log.info(
            "maintenance done",
            extra={"conversations": removed, "request_ids": requests, "rate_windows": windows},
        )

    return run


async def serve(settings: Settings) -> None:
    database = conninfo(settings)
    applied = await asyncio.to_thread(apply_migrations, database, schema="agent")
    if applied:
        log.info("migrations applied", extra={"migrations": applied})
    messages = load_messages(settings.messages_file)
    models = create_models(settings)
    embedder = await asyncio.to_thread(
        FastEmbedEmbedder,
        settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    pool = await open_pool(settings, max_size=settings.max_concurrent_requests + 2)
    stack = contextlib.AsyncExitStack()
    try:
        stack.push_async_callback(pool.close)
        knowledge = KnowledgeRepository(pool)
        indexed_with = await knowledge.get_meta(META_EMBEDDING_MODEL)
        if indexed_with not in (None, settings.embedding_model):
            log.error(
                "the knowledge base was indexed with another embedding model; run an ingestion",
                extra={"indexed_with": indexed_with, "configured": settings.embedding_model},
            )
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(database, serde=checkpoint_serializer())
        )
        await checkpointer.setup()
        deps = Dependencies(
            main_model=models.main,
            fast_model=models.fast,
            search=KnowledgeSearch(
                pool,
                embedder,
                candidates=settings.retrieval_candidates,
                top_k=settings.retrieval_top_k,
            ),
            messages=messages,
            history_turns=settings.history_turns,
            referral_min_score=settings.referral_min_score,
        )
        conversations = ConversationStore(pool, settings.conversation_ttl)
        processed = ProcessedRequests(pool)
        rate_limiter = RateLimiter(pool, settings.max_requests_per_minute)
        producer = await start_producer(settings, client_id=KAFKA_CLIENT_ID)
        stack.push_async_callback(producer.stop)
        consumer = await start_consumer(
            settings, REQUESTS_TOPIC, client_id=KAFKA_CLIENT_ID, group_id=CONSUMER_GROUP
        )
        stack.push_async_callback(consumer.stop)
        processor = RequestProcessor(
            graph=build_graph(deps, checkpointer),
            conversations=conversations,
            processed=processed,
            rate_limiter=rate_limiter,
            audit_log=AuditLog(pool),
            personas=knowledge,
            publisher=KafkaPublisher(producer),
            messages=messages,
            llm_model=models.main_name,
            max_question_chars=settings.max_question_chars,
            answer_timeout=settings.answer_timeout,
        )
        worker = AgentWorker(
            consumer,
            processor.process,
            max_concurrent=settings.max_concurrent_requests,
            maintenance=maintenance_task(conversations, processed, rate_limiter, checkpointer),
            heartbeat=settings.heartbeat_file,
        )
        stop = asyncio.Event()
        _stop_on_signals(stop)
        log.info("agent worker started", extra={"model": models.main_name})
        await worker.run(stop)
    finally:
        await stack.aclose()


def _stop_on_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Windows' event loops do not support signal handlers: Ctrl+C stops the process there.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


def main() -> None:
    settings = bootstrap()
    with contextlib.suppress(KeyboardInterrupt):
        run_async(serve(settings))
