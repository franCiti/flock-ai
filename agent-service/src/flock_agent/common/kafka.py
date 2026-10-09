"""Kafka producers and consumers over mutual TLS (plan sections 2.2 and 7.2)."""

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
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
