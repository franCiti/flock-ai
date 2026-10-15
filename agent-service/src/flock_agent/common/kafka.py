"""Kafka producers and consumers over mutual TLS (plan sections 2.2 and 7.2)."""

from collections import deque

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from pydantic import BaseModel

from flock_agent.common.settings import Settings
from flock_agent.common.tls import TlsFiles, client_ssl_context

CONTENT_TYPE = "application/json"

Headers = list[tuple[str, bytes]]


def _connection_options(settings: Settings, client_id: str) -> dict[str, object]:
    return {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "client_id": client_id,
        "security_protocol": "SSL",
        "ssl_context": client_ssl_context(TlsFiles.from_settings(settings)),
    }


async def start_producer(settings: Settings, *, client_id: str) -> AIOKafkaProducer:
    """Started producer that waits for every replica and never duplicates on retries."""
    producer = AIOKafkaProducer(
        **_connection_options(settings, client_id),
        acks="all",
        enable_idempotence=True,
    )
    await producer.start()
    return producer


async def start_consumer(
    settings: Settings,
    *topics: str,
    client_id: str,
    group_id: str | None,
) -> AIOKafkaConsumer:
    """Started consumer. Offsets are committed explicitly by the caller, after processing.

    With group_id=None the consumer belongs to no group: it gets every partition of the topics and
    commits nothing (used by tools and tests, so they never move a service's offsets).
    """
    consumer = AIOKafkaConsumer(
        *topics,
        **_connection_options(settings, client_id),
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    return consumer


def message_headers(schema: str) -> Headers:
    """Headers of every contract message: content type and payload schema (plan 2.2)."""
    return [("content-type", CONTENT_TYPE.encode()), ("schema", schema.encode())]


def encode_message(message: BaseModel) -> bytes:
    """Serialize a contract model with its wire (camelCase) field names."""
    return message.model_dump_json(by_alias=True, exclude_unset=True).encode()


class KafkaPublisher:
    """Publishes contract messages with their headers and waits for the broker's ack."""

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self._producer = producer

    async def publish(self, topic: str, key: str | None, message: BaseModel, schema: str) -> None:
        await self._producer.send_and_wait(
            topic,
            value=encode_message(message),
            key=None if key is None else key.encode(),
            headers=message_headers(schema),
        )


class OffsetTracker:
    """Which offsets can be committed: those below the oldest message still being handled.

    Messages finish in any order, but a partition's offset can only move past a message once
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
