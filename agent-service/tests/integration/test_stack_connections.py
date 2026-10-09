"""Connections to the real stack: mutual TLS, PostgreSQL roles and Kafka ACLs (task T08)."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import psycopg
import pytest
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.errors import TopicAuthorizationFailedError
from psycopg import sql

from flock_agent.common.db import conninfo, open_pool
from flock_agent.common.kafka import encode_message, message_headers, start_consumer, start_producer
from flock_agent.common.settings import Settings
from flock_agent.contracts.generated.agent_request_v1 import AgentRequest

# Provided by the stack_settings fixture (conftest.py): settings for a given certificate.
StackSettings = Callable[..., Settings]

pytestmark = pytest.mark.integration_stack


# --- PostgreSQL -----------------------------------------------------------------------------


async def test_each_certificate_logs_in_as_its_role(stack_settings: StackSettings) -> None:
    for cert, role in [("agent", "agent"), ("ingestion", "ingestion")]:
        pool = await open_pool(stack_settings(cert, postgres_user=role), max_size=1)
        try:
            async with pool.connection() as connection:
                cursor = await connection.execute(
                    "SELECT current_user, ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
                )
                assert await cursor.fetchone() == (role, True)
        finally:
            await pool.close()


async def test_a_certificate_cannot_log_in_as_another_role(stack_settings: StackSettings) -> None:
    settings = stack_settings("agent", postgres_user="ingestion")

    with pytest.raises(psycopg.OperationalError, match="authentication failed"):
        await psycopg.AsyncConnection.connect(conninfo(settings))


async def test_the_agent_reads_but_cannot_write_the_knowledge_base(
    stack_settings: StackSettings,
) -> None:
    table = sql.Identifier("knowledge", f"t08_{uuid.uuid4().hex[:12]}")
    ingestion = await open_pool(stack_settings("ingestion", postgres_user="ingestion"), max_size=1)
    agent = await open_pool(stack_settings("agent", postgres_user="agent"), max_size=1)
    try:
        async with ingestion.connection() as connection:
            await connection.execute(sql.SQL("CREATE TABLE {} (id int)").format(table))
            await connection.execute(sql.SQL("INSERT INTO {} VALUES (1)").format(table))

        async with agent.connection() as connection:
            cursor = await connection.execute(sql.SQL("SELECT count(*) FROM {}").format(table))
            assert await cursor.fetchone() == (1,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await connection.execute(sql.SQL("INSERT INTO {} VALUES (2)").format(table))
    finally:
        async with ingestion.connection() as connection:
            await connection.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table))
        await asyncio.gather(ingestion.close(), agent.close())


# --- Kafka ----------------------------------------------------------------------------------


WAIT_SECONDS = 20


async def read_from_end(consumer: AIOKafkaConsumer) -> None:
    """Wait until every partition is assigned (no group: all of them) and skip existing records."""
    async with asyncio.timeout(WAIT_SECONDS):
        # aiokafka exposes no event for the no-group assignment: polling is the only way.
        while not consumer.assignment():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
    await consumer.seek_to_end()


async def wait_for_key(consumer: AIOKafkaConsumer, key: bytes) -> ConsumerRecord[bytes, bytes]:
    async with asyncio.timeout(WAIT_SECONDS):
        while True:
            batches = await consumer.getmany(timeout_ms=1000)
            for records in batches.values():
                for record in records:
                    if record.key == key:
                        return record


def sample_request() -> AgentRequest:
    return AgentRequest.model_validate(
        {
            "version": 1,
            "requestId": str(uuid.uuid4()),
            "conversationId": f"t08-{uuid.uuid4().hex[:8]}",
            "personaId": "juan-plataforma",
            "question": "¿Cómo hago rollback de un deploy?",
            "replyTo": "agent.replies.cli",
            "sentAt": datetime.now(UTC).isoformat(),
        }
    )


async def test_a_client_request_reaches_the_agent(stack_settings: StackSettings) -> None:
    request = sample_request()
    key = request.conversation_id.encode()
    consumer = await start_consumer(
        stack_settings("agent"), "agent.requests", client_id="t08-agent", group_id=None
    )
    producer = await start_producer(stack_settings("cli"), client_id="t08-cli")
    try:
        await read_from_end(consumer)
        await producer.send_and_wait(
            "agent.requests",
            encode_message(request),
            key=key,
            headers=message_headers("agent-request.v1"),
        )

        record = await wait_for_key(consumer, key)

        assert AgentRequest.model_validate_json(record.value) == request
        assert dict(record.headers)["schema"] == b"agent-request.v1"
    finally:
        await asyncio.gather(producer.stop(), consumer.stop())


async def test_the_agent_replies_to_the_client_topic(stack_settings: StackSettings) -> None:
    key = f"t08-{uuid.uuid4().hex[:8]}".encode()
    consumer = await start_consumer(
        stack_settings("cli"), "agent.replies.cli", client_id="t08-cli", group_id=None
    )
    producer = await start_producer(stack_settings("agent"), client_id="t08-agent")
    try:
        await read_from_end(consumer)
        await producer.send_and_wait("agent.replies.cli", b'{"probe": true}', key=key)

        record = await wait_for_key(consumer, key)

        assert record.value == b'{"probe": true}'
    finally:
        await asyncio.gather(producer.stop(), consumer.stop())


async def test_acls_reject_a_service_writing_where_it_must_not(
    stack_settings: StackSettings,
) -> None:
    producer = await start_producer(stack_settings("ingestion"), client_id="t08-ingestion")
    try:
        with pytest.raises(TopicAuthorizationFailedError):
            await producer.send_and_wait("agent.requests", b"{}", key=b"t08")
    finally:
        await producer.stop()
