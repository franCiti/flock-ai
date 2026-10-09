"""Embedding model control of the knowledge base (task T10, plan 3.2 and 5.5)."""

from datetime import UTC, datetime

import psycopg
import pytest

from flock_agent.knowledge.index_model import ensure_embedding_model
from flock_agent.knowledge.models import ChunkInput, DocumentRecord, Persona
from flock_agent.knowledge.repository import (
    META_DIMENSIONS,
    META_EMBEDDING_MODEL,
    KnowledgeRepository,
)
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.integration_containers

PERSONA = Persona(id="juan-plataforma", display_name="Juan", profile_hash="h")
DOCUMENT = DocumentRecord(
    id="file:juan-plataforma:deploy.md",
    persona_id="juan-plataforma",
    source_type="file",
    title="Deploy",
    source_updated_at=datetime(2026, 10, 9, tzinfo=UTC),
    content_hash="c1",
)


async def index_one_document(repository: KnowledgeRepository, dimensions: int) -> None:
    await repository.upsert_persona(PERSONA)
    await repository.replace_document(
        DOCUMENT, [ChunkInput(ordinal=0, content="deploy", embedding=[0.1] * dimensions)]
    )
    await repository.save_sync_state(PERSONA.id, "folder", {"files": {"deploy.md": 1}})


@pytest.fixture
async def knowledge_384(knowledge: KnowledgeRepository) -> KnowledgeRepository:
    """Knowledge base indexed with a 384-dimension model (and restored to 384 afterwards)."""
    await ensure_embedding_model(knowledge, FakeEmbedder("model-384", 384))
    return knowledge


async def test_the_first_run_records_the_model(knowledge: KnowledgeRepository) -> None:
    assert await ensure_embedding_model(knowledge, FakeEmbedder("model-a", 384)) is True

    assert await knowledge.get_meta(META_EMBEDDING_MODEL) == "model-a"
    assert await knowledge.get_meta(META_DIMENSIONS) == "384"


async def test_the_same_model_keeps_the_knowledge(knowledge_384: KnowledgeRepository) -> None:
    await index_one_document(knowledge_384, 384)

    assert await ensure_embedding_model(knowledge_384, FakeEmbedder("model-384", 384)) is False

    assert await knowledge_384.document_ids(PERSONA.id, None) == {DOCUMENT.id}
    assert await knowledge_384.get_sync_state(PERSONA.id, "folder") is not None


async def test_another_model_resets_the_knowledge_but_keeps_personas(
    knowledge_384: KnowledgeRepository,
) -> None:
    await index_one_document(knowledge_384, 384)

    try:
        assert await ensure_embedding_model(knowledge_384, FakeEmbedder("model-8", 8)) is True

        assert await knowledge_384.document_ids(PERSONA.id, None) == set()
        assert await knowledge_384.get_sync_state(PERSONA.id, "folder") is None
        assert await knowledge_384.get_persona(PERSONA.id) == PERSONA
        assert await knowledge_384.get_meta(META_EMBEDDING_MODEL) == "model-8"
        assert await knowledge_384.get_meta(META_DIMENSIONS) == "8"

        # The vector column now takes the new dimensions, and only those.
        await index_one_document(knowledge_384, 8)
        with pytest.raises(psycopg.errors.DataException):
            await index_one_document(knowledge_384, 384)
    finally:
        # The test database is shared by the session: leave the 384-dimension column.
        await ensure_embedding_model(knowledge_384, FakeEmbedder("model-384", 384))
