"""Knowledge base schema and repository (task T09, plan section 3.2)."""

import asyncio
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from flock_agent.common.db import Pool
from flock_agent.common.migrations import apply_migrations
from flock_agent.knowledge.models import ChunkInput, DocumentRecord, Persona
from flock_agent.knowledge.repository import IngestionAlreadyRunningError, KnowledgeRepository
from tests.integration.containers import TestDatabase

pytestmark = pytest.mark.integration_containers

DIMENSIONS = 384


def persona(persona_id: str = "juan-plataforma", **changes: object) -> Persona:
    values: dict[str, object] = {
        "id": persona_id,
        "display_name": "Juan Pérez",
        "identities": {"email": "juan@example.com"},
        "profile_hash": "h1",
    }
    return Persona.model_validate(values | changes)


def document(
    document_id: str = "file:juan-plataforma:deploy.md", **changes: object
) -> DocumentRecord:
    values: dict[str, object] = {
        "id": document_id,
        "persona_id": "juan-plataforma",
        "source_type": "file",
        "title": "Deploy",
        "path": "deploy.md",
        "source_updated_at": datetime(2026, 10, 9, tzinfo=UTC),
        "content_hash": "c1",
    }
    return DocumentRecord.model_validate(values | changes)


def chunks(*texts: str) -> list[ChunkInput]:
    return [
        ChunkInput(ordinal=i, heading_path="Deploy", content=text, embedding=[0.1] * DIMENSIONS)
        for i, text in enumerate(texts)
    ]


async def chunk_texts(repository: KnowledgeRepository, document_id: str) -> list[str]:
    async with repository._pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT content FROM chunk WHERE document_id = %s ORDER BY ordinal", (document_id,)
        )
        return [row[0] for row in await cursor.fetchall()]


async def count(repository: KnowledgeRepository, table: str) -> int:
    async with repository._pool.connection() as connection:
        query = psycopg.sql.SQL("SELECT count(*) FROM {}").format(psycopg.sql.Identifier(table))
        cursor = await connection.execute(query)
        row = await cursor.fetchone()
        assert row is not None
        return int(row[0])


# --- Migrations -----------------------------------------------------------------------------


def test_migrations_are_idempotent(test_database: TestDatabase) -> None:
    assert apply_migrations(test_database.conninfo("ingestion"), schema="knowledge") == []


async def test_the_agent_can_read_but_not_write(
    knowledge: KnowledgeRepository, agent_pool: Pool
) -> None:
    await knowledge.upsert_persona(persona())

    async with agent_pool.connection() as connection:
        cursor = await connection.execute("SELECT display_name FROM knowledge.persona")
        assert await cursor.fetchall() == [("Juan Pérez",)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await connection.execute("DELETE FROM knowledge.chunk")


# --- Personas -------------------------------------------------------------------------------


async def test_upsert_persona_creates_and_updates(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.upsert_persona(persona(display_name="Juan P.", profile_hash="h2"))

    assert await knowledge.get_persona("juan-plataforma") == persona(
        display_name="Juan P.", profile_hash="h2"
    )
    assert await knowledge.list_personas() == [persona(display_name="Juan P.", profile_hash="h2")]


async def test_unknown_persona_is_none(knowledge: KnowledgeRepository) -> None:
    assert await knowledge.get_persona("nobody") is None


async def test_deleting_a_persona_deletes_its_knowledge_in_cascade(
    knowledge: KnowledgeRepository,
) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.replace_document(document(), chunks("a", "b"))
    await knowledge.save_sync_state("juan-plataforma", "folder", {"files": {}})

    await knowledge.delete_persona("juan-plataforma")

    for table in ("persona", "document", "chunk", "sync_state"):
        assert await count(knowledge, table) == 0


# --- Documents and chunks -------------------------------------------------------------------


async def test_replace_document_stores_and_replaces_its_chunks(
    knowledge: KnowledgeRepository,
) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.replace_document(document(), chunks("one", "two", "three"))

    await knowledge.replace_document(document(content_hash="c2"), chunks("new one"))

    assert await chunk_texts(knowledge, document().id) == ["new one"]
    assert await knowledge.get_content_hash(document().id) == "c2"


async def test_a_failed_replace_keeps_the_previous_version(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.replace_document(document(), chunks("one", "two"))
    broken = [ChunkInput(ordinal=0, content="wrong", embedding=[0.1] * (DIMENSIONS - 1))]

    with pytest.raises(psycopg.errors.DataException):
        await knowledge.replace_document(document(content_hash="c2"), broken)

    assert await chunk_texts(knowledge, document().id) == ["one", "two"]
    assert await knowledge.get_content_hash(document().id) == "c1"


async def test_readers_never_see_a_half_replaced_document(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.replace_document(document(), chunks("old 1", "old 2"))
    seen: set[tuple[str, ...]] = set()

    async def read_repeatedly() -> None:
        for _ in range(200):
            seen.add(tuple(await chunk_texts(knowledge, document().id)))

    async def replace_repeatedly() -> None:
        for i in range(30):
            version = chunks("old 1", "old 2") if i % 2 else chunks("new 1", "new 2", "new 3")
            await knowledge.replace_document(document(), version)

    await asyncio.gather(read_repeatedly(), replace_repeatedly())

    assert seen <= {("old 1", "old 2"), ("new 1", "new 2", "new 3")}


async def test_deleting_an_email_deletes_its_attachments(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    email = document("file:juan-plataforma:mail.eml", source_type="email")
    attachment = document(
        "file:juan-plataforma:mail.eml#attachment/plan.pdf",
        source_type="email_attachment",
        parent_id=email.id,
    )
    await knowledge.replace_document(email, chunks("mail"))
    await knowledge.replace_document(attachment, chunks("pdf"))

    assert await knowledge.delete_documents([email.id]) == 1

    assert await count(knowledge, "document") == 0
    assert await count(knowledge, "chunk") == 0


async def test_chunks_cannot_belong_to_another_persona(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.upsert_persona(persona("ana-datos", display_name="Ana"))
    await knowledge.replace_document(document(), chunks("a"))

    async with knowledge._pool.connection() as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await connection.execute(
                """
                INSERT INTO chunk (document_id, persona_id, ordinal, content, embedding)
                VALUES (%s, 'ana-datos', 1, 'leak', %s::vector)
                """,
                (document().id, str([0.1] * DIMENSIONS)),
            )


async def test_documents_by_source_and_removed_sources(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    await knowledge.replace_document(document(), chunks("folder file"))
    for source_id in ("src-jira", "src-wiki"):
        await knowledge.replace_document(
            document(f"{source_id}:juan-plataforma:1", source_type="jira", source_id=source_id),
            chunks("issue"),
        )

    assert await knowledge.document_ids("juan-plataforma", None) == {document().id}
    assert await knowledge.document_ids("juan-plataforma", "src-jira") == {
        "src-jira:juan-plataforma:1"
    }

    deleted = await knowledge.delete_documents_of_other_sources("juan-plataforma", ["src-jira"])

    assert deleted == 1
    assert await knowledge.document_ids("juan-plataforma", "src-wiki") == set()
    assert await knowledge.document_ids("juan-plataforma", None) == {document().id}


# --- Sync state, runs, meta -----------------------------------------------------------------


async def test_sync_state_is_saved_and_updated(knowledge: KnowledgeRepository) -> None:
    await knowledge.upsert_persona(persona())
    assert await knowledge.get_sync_state("juan-plataforma", "folder") is None

    await knowledge.save_sync_state("juan-plataforma", "folder", {"files": {"a.md": 1}})
    await knowledge.save_sync_state("juan-plataforma", "folder", {"files": {"a.md": 2}})

    state = await knowledge.get_sync_state("juan-plataforma", "folder")
    assert state is not None
    assert state.cursor == {"files": {"a.md": 2}}


async def test_ingestion_runs_are_recorded(knowledge: KnowledgeRepository) -> None:
    job_id = uuid.uuid4()
    await knowledge.start_run(job_id, "manual")
    await knowledge.finish_run(job_id, "completed", {"personas": 1})

    run = await knowledge.get_run(job_id)

    assert run is not None
    assert (run.trigger, run.status, run.summary) == ("manual", "completed", {"personas": 1})
    assert run.finished_at is not None


async def test_meta_values(knowledge: KnowledgeRepository) -> None:
    assert await knowledge.get_meta("embedding_model") is None

    await knowledge.set_meta("embedding_model", "model-a")
    await knowledge.set_meta("embedding_model", "model-b")

    assert await knowledge.get_meta("embedding_model") == "model-b"


# --- Ingestion lock -------------------------------------------------------------------------


async def test_only_one_ingestion_at_a_time(
    knowledge: KnowledgeRepository, test_database: TestDatabase
) -> None:
    other_process = KnowledgeRepository(knowledge._pool)

    async with knowledge.ingestion_lock():
        with pytest.raises(IngestionAlreadyRunningError):
            async with other_process.ingestion_lock():
                pass

    async with other_process.ingestion_lock():
        pass  # released when the first block ended
