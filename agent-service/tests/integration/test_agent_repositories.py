"""Agent schema: conversations, idempotency, rate limits and audit (task T19, plan 3.3)."""

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from flock_agent.agent.audit import AuditLog
from flock_agent.agent.conversations import ConversationStore, thread_id
from flock_agent.agent.idempotency import ProcessedRequests
from flock_agent.agent.rate_limit import RateLimiter, window_start
from flock_agent.common.db import Pool
from flock_agent.common.migrations import apply_migrations
from flock_agent.contracts.generated.audit_entry_v1 import AuditEntry
from tests.integration.containers import TestDatabase

pytestmark = pytest.mark.integration_containers

T0 = datetime(2026, 10, 9, 12, 0, 30, tzinfo=UTC)
TTL = timedelta(days=1)


async def generation(
    store: ConversationStore,
    at: datetime,
    *,
    client: str = "core-api",
    conversation: str = "c1",
    persona: str = "juan-plataforma",
) -> int:
    return (await store.resolve(client, conversation, persona, at=at)).generation


# --- Migrations -----------------------------------------------------------------------------


def test_migrations_are_idempotent(test_database: TestDatabase) -> None:
    assert apply_migrations(test_database.conninfo("agent"), schema="agent") == []


async def test_other_roles_cannot_read_the_agent_schema(
    test_database: TestDatabase, agent_tables: Pool
) -> None:
    async with await psycopg.AsyncConnection.connect(
        test_database.conninfo("ingestion")
    ) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await connection.execute("SELECT * FROM agent.audit_entry")


# --- Conversations (spec HU5.3) -------------------------------------------------------------


async def test_a_new_conversation_starts_at_generation_zero(agent_tables: Pool) -> None:
    thread = await ConversationStore(agent_tables, TTL).resolve(
        "core-api", "c1", "juan-plataforma", at=T0
    )
    assert thread.generation == 0
    assert thread.thread_id == "core-api:c1:0" == thread_id("core-api", "c1", 0)


async def test_retention_counts_from_the_last_message(agent_tables: Pool) -> None:
    store = ConversationStore(agent_tables, TTL)
    assert await generation(store, T0) == 0
    # Each message keeps it alive for another TTL: 40 h after the first one, same thread.
    assert await generation(store, T0 + timedelta(hours=20)) == 0
    assert await generation(store, T0 + timedelta(hours=40)) == 0
    # Exactly the TTL is still within it; more than the TTL starts without history.
    assert await generation(store, T0 + timedelta(hours=64)) == 0
    assert await generation(store, T0 + timedelta(hours=88, seconds=1)) == 1
    assert await generation(store, T0 + timedelta(hours=89)) == 1


async def test_asking_another_persona_starts_without_history(agent_tables: Pool) -> None:
    store = ConversationStore(agent_tables, TTL)
    assert await generation(store, T0) == 0
    assert await generation(store, T0 + timedelta(minutes=1), persona="maria-datos") == 1
    assert await generation(store, T0 + timedelta(minutes=2), persona="maria-datos") == 1
    assert await generation(store, T0 + timedelta(minutes=3)) == 2


async def test_two_apps_can_use_the_same_conversation_id(agent_tables: Pool) -> None:
    store = ConversationStore(agent_tables, TTL)
    assert await generation(store, T0, client="app-a") == 0
    assert await generation(store, T0, client="app-b", persona="maria-datos") == 0
    assert await generation(store, T0 + timedelta(minutes=1), client="app-a") == 0


async def test_purge_deletes_the_threads_of_expired_conversations(agent_tables: Pool) -> None:
    store = ConversationStore(agent_tables, TTL)
    await generation(store, T0, conversation="old")
    await generation(store, T0 + timedelta(minutes=1), conversation="old", persona="maria-datos")
    await generation(store, T0 + timedelta(hours=23), conversation="active")
    deleted: list[str] = []

    async def delete_threads(thread_ids: Sequence[str]) -> None:
        deleted.extend(thread_ids)

    now = T0 + timedelta(days=1, minutes=2)
    assert await store.purge_expired(delete_threads, at=now) == 1
    assert sorted(deleted) == ["core-api:old:0", "core-api:old:1"]
    # The active conversation keeps its thread; the purged one starts over.
    assert await generation(store, now, conversation="active") == 0
    assert await generation(store, now, conversation="old") == 0


async def test_purge_keeps_a_conversation_that_got_a_question_meanwhile(
    agent_tables: Pool,
) -> None:
    store = ConversationStore(agent_tables, TTL)
    await generation(store, T0)
    now = T0 + timedelta(days=2)

    async def question_arrives(thread_ids: Sequence[str]) -> None:
        assert list(thread_ids) == ["core-api:c1:0"]
        assert await generation(store, now) == 1

    assert await store.purge_expired(question_arrives, at=now) == 0
    assert await generation(store, now + timedelta(minutes=1)) == 1


async def test_purge_without_expired_conversations_does_nothing(agent_tables: Pool) -> None:
    store = ConversationStore(agent_tables, TTL)
    await generation(store, T0)

    async def unexpected(thread_ids: Sequence[str]) -> None:
        raise AssertionError(thread_ids)

    assert await store.purge_expired(unexpected, at=T0 + timedelta(hours=1)) == 0


# --- Processed requests (spec, edge case: repeated request) ---------------------------------


async def test_a_request_is_recorded_once(agent_tables: Pool) -> None:
    requests = ProcessedRequests(agent_tables)
    request_id = uuid.uuid4()
    assert not await requests.contains(request_id)
    assert await requests.add(request_id, "core-api", at=T0)
    assert await requests.contains(request_id)
    assert not await requests.add(request_id, "core-api", at=T0 + timedelta(seconds=5))


async def test_processed_requests_are_forgotten_after_seven_days(agent_tables: Pool) -> None:
    requests = ProcessedRequests(agent_tables)
    old, recent = uuid.uuid4(), uuid.uuid4()
    await requests.add(old, "core-api", at=T0)
    await requests.add(recent, "core-api", at=T0 + timedelta(days=1))
    assert await requests.purge(at=T0 + timedelta(days=7, seconds=1)) == 1
    assert not await requests.contains(old)
    assert await requests.contains(recent)


# --- Rate limit per client app (spec HU15.5) ------------------------------------------------


def test_window_start_is_the_minute_in_utc() -> None:
    local = datetime(2026, 10, 9, 9, 15, 42, 123, tzinfo=UTC).astimezone()
    assert window_start(local) == datetime(2026, 10, 9, 9, 15, tzinfo=UTC)


async def test_the_limit_applies_per_minute(agent_tables: Pool) -> None:
    limiter = RateLimiter(agent_tables, max_per_minute=3)
    minute = window_start(T0)
    results = [
        await limiter.acquire("core-api", at=minute + timedelta(seconds=s)) for s in (0, 10, 20, 59)
    ]
    assert results == [True, True, True, False]
    # A new window starts on the next minute.
    assert await limiter.acquire("core-api", at=minute + timedelta(minutes=1))


async def test_each_app_has_its_own_limit(agent_tables: Pool) -> None:
    limiter = RateLimiter(agent_tables, max_per_minute=1)
    assert await limiter.acquire("app-a", at=T0)
    assert not await limiter.acquire("app-a", at=T0)
    assert await limiter.acquire("app-b", at=T0)


async def test_concurrent_requests_never_exceed_the_limit(agent_tables: Pool) -> None:
    limiter = RateLimiter(agent_tables, max_per_minute=5)
    results = await asyncio.gather(*(limiter.acquire("core-api", at=T0) for _ in range(12)))
    assert results.count(True) == 5


async def test_purge_keeps_only_the_current_window(agent_tables: Pool) -> None:
    limiter = RateLimiter(agent_tables, max_per_minute=1)
    await limiter.acquire("core-api", at=T0 - timedelta(minutes=1))
    await limiter.acquire("core-api", at=T0)
    assert await limiter.purge(at=T0) == 1
    assert not await limiter.acquire("core-api", at=T0)


# --- Audit log (spec HU8, HU15.7) -----------------------------------------------------------


def audit_entry(**changes: object) -> AuditEntry:
    values: dict[str, object] = {
        "version": 1,
        "auditId": uuid.uuid4(),
        "requestId": uuid.uuid4(),
        "clientId": "core-api",
        "conversationId": "c1",
        "personaId": "juan-plataforma",
        "question": "¿Cómo hago un deploy?",
        "answer": "Con el pipeline de release [1].",
        "outcome": "answered",
        "errorCode": None,
        "citations": [
            {
                "documentId": "file:juan-plataforma:deploy.md",
                "title": "Deploy",
                "path": "deploy.md",
                "section": "Deploy > Rollback",
                "sourceType": "file",
            },
            {
                "documentId": "jira:juan-plataforma:OPS-1",
                "title": "OPS-1",
                "url": "https://jira.example.com/browse/OPS-1",
                "sourceType": "jira",
            },
        ],
        "referralPersonaId": None,
        "flags": [],
        "llmModel": "fake-model",
        "promptVersion": "v1",
        "firstTokenMs": 850,
        "totalMs": 4200,
        "createdAt": T0,
    }
    return AuditEntry.model_validate(values | changes)


async def test_an_answer_is_recorded_with_its_sources(agent_tables: Pool) -> None:
    log = AuditLog(agent_tables)
    entry = audit_entry(referralPersonaId="maria-datos", flags=["injection_suspected"])
    await log.record(entry)
    assert await log.get(entry.audit_id) == entry


async def test_an_unreadable_request_is_recorded_without_identifiers(agent_tables: Pool) -> None:
    log = AuditLog(agent_tables)
    entry = audit_entry(
        requestId=None,
        clientId=None,
        conversationId=None,
        personaId=None,
        question=None,
        answer=None,
        outcome="error",
        errorCode="INVALID_REQUEST",
        citations=[],
        flags=["invalid_request"],
        llmModel=None,
        promptVersion=None,
        firstTokenMs=None,
        totalMs=None,
    )
    await log.record(entry)
    assert await log.get(entry.audit_id) == entry


async def test_recording_the_same_entry_twice_keeps_one(agent_tables: Pool) -> None:
    log = AuditLog(agent_tables)
    entry = audit_entry()
    await log.record(entry)
    await log.record(entry)
    async with agent_tables.connection() as connection:
        cursor = await connection.execute("SELECT count(*) FROM audit_entry")
        assert await cursor.fetchone() == (1,)


async def test_unknown_audit_entry_is_none(agent_tables: Pool) -> None:
    assert await AuditLog(agent_tables).get(uuid.uuid4()) is None
