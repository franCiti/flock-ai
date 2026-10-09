"""Hybrid search, always filtered by persona (task T21, plan 4.3 and 4.8, spec HU2 and HU3).

The search runs as the agent role (read-only). The fake embedder has no notion of meaning, so
"by meaning" is checked with the real model (marker embedding_model).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from flock_agent.common.db import Pool
from flock_agent.common.settings import Settings
from flock_agent.knowledge.embeddings import Embedder, FastEmbedEmbedder
from flock_agent.knowledge.models import ChunkInput, DocumentRecord, Persona
from flock_agent.knowledge.repository import KnowledgeRepository
from flock_agent.knowledge.search import KnowledgeSearch
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.integration_containers

REPO_ROOT = Path(__file__).resolve().parents[3]

JUAN = "juan-plataforma"
ANA = "ana-datos"
PEDRO = "pedro-redes"

ROLLBACK = "[Deploy > Rollback] Para revertir un deploy fallido, ejecutá el job rollback-prod."
HOLIDAYS = "[Vacaciones] Las vacaciones se piden con dos semanas de anticipación en RRHH."
ERROR_502 = "[Errores] El código ERR_502 aparece cuando el balanceador no llega al backend."
ON_CALL = "[Guardias] La guardia rota cada semana; el calendario está en la wiki."
QUALITY = "[Calidad] Las validaciones de calidad corren todas las noches con el job dq-nightly."
ANA_502 = "[Errores] El código ERR_502 también aparece en las cargas del data lake."
VPN = "[VPN] La VPN corporativa se configura con el cliente de la intranet."

KNOWLEDGE = {
    JUAN: {
        "deploy.md": ROLLBACK,
        "vacaciones.md": HOLIDAYS,
        "errores.md": ERROR_502,
        "guardias.md": ON_CALL,
    },
    ANA: {"calidad.md": QUALITY, "errores.md": ANA_502},
    PEDRO: {"vpn.md": VPN},
}
NAMES = {JUAN: "Juan Pérez", ANA: "Ana Gómez", PEDRO: "Pedro Ruiz"}


async def index(
    knowledge: KnowledgeRepository, embedder: Embedder, documents: dict[str, dict[str, str]]
) -> None:
    for persona_id, files in documents.items():
        await knowledge.upsert_persona(
            Persona(id=persona_id, display_name=NAMES.get(persona_id, persona_id), profile_hash="h")
        )
        for path, text in files.items():
            await knowledge.replace_document(
                DocumentRecord(
                    id=f"file:{persona_id}:{path}",
                    persona_id=persona_id,
                    source_type="file",
                    title=path,
                    path=path,
                    source_updated_at=datetime(2026, 10, 9, tzinfo=UTC),
                    content_hash="c",
                ),
                [
                    ChunkInput(
                        ordinal=0,
                        heading_path=path,
                        content=text,
                        embedding=embedder.embed_documents([text])[0],
                    )
                ],
            )


@pytest.fixture
async def fake_search(knowledge: KnowledgeRepository, agent_pool: Pool) -> KnowledgeSearch:
    embedder = FakeEmbedder()
    await index(knowledge, embedder, KNOWLEDGE)
    return KnowledgeSearch(agent_pool, embedder, candidates=20, top_k=8)


@pytest.fixture(scope="module")
def real_embedder() -> FastEmbedEmbedder:
    model = Settings(_env_file=None).embedding_model
    return FastEmbedEmbedder(model, cache_dir=REPO_ROOT / "data" / "models")


# --- Search in one persona (retrieve) -------------------------------------------------------


@pytest.mark.embedding_model
async def test_finds_by_meaning(
    knowledge: KnowledgeRepository, agent_pool: Pool, real_embedder: FastEmbedEmbedder
) -> None:
    await index(knowledge, real_embedder, KNOWLEDGE)
    search = KnowledgeSearch(agent_pool, real_embedder, candidates=20, top_k=8)
    # No word in common with the fragment: only the meaning can find it.
    hits = await search.search(JUAN, "How do I undo a broken release?")
    assert hits[0].content == ROLLBACK


async def test_finds_by_exact_term(fake_search: KnowledgeSearch) -> None:
    hits = await fake_search.search(JUAN, "¿Qué significa ERR_502?")
    assert hits[0].content == ERROR_502
    assert hits[0].document_id == f"file:{JUAN}:errores.md"
    assert hits[0].title == "errores.md"
    assert hits[0].path == "errores.md"
    assert hits[0].source_type == "file"


async def test_finds_terms_with_hyphens(fake_search: KnowledgeSearch) -> None:
    hits = await fake_search.search(JUAN, "rollback-prod")
    assert hits[0].content == ROLLBACK


async def test_never_returns_fragments_of_another_persona(fake_search: KnowledgeSearch) -> None:
    for query in ("dq-nightly", "ERR_502 data lake", QUALITY, "VPN corporativa"):
        hits = await fake_search.search(JUAN, query)
        assert hits
        assert {hit.persona_id for hit in hits} == {JUAN}
        assert all(hit.document_id.startswith(f"file:{JUAN}:") for hit in hits)


async def test_returns_at_most_top_k_fragments(
    knowledge: KnowledgeRepository, agent_pool: Pool
) -> None:
    embedder = FakeEmbedder()
    notes = {f"nota-{i}.md": f"[Nota {i}] Procedimiento número {i} del deploy." for i in range(30)}
    await index(knowledge, embedder, {JUAN: notes})
    hits = await KnowledgeSearch(agent_pool, embedder, candidates=20, top_k=8).search(
        JUAN, "deploy"
    )
    assert len(hits) == 8
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


async def test_a_persona_without_knowledge_finds_nothing(fake_search: KnowledgeSearch) -> None:
    assert await fake_search.search("sin-documentos", "¿Cómo hago un deploy?") == []


async def test_a_question_of_common_words_only_searches_by_meaning(
    fake_search: KnowledgeSearch,
) -> None:
    hits = await fake_search.search(JUAN, "¿Qué es esto?")
    assert len(hits) == len(KNOWLEDGE[JUAN])


# --- Search in the other personas (find_referral) -------------------------------------------


async def test_other_personas_never_include_the_one_asked(fake_search: KnowledgeSearch) -> None:
    matches = await fake_search.search_other_personas(JUAN, "dq-nightly")
    assert matches[0].persona_id == ANA
    assert matches[0].display_name == "Ana Gómez"
    assert matches[0].hits[0].content == QUALITY
    assert JUAN not in {match.persona_id for match in matches}
    for match in matches:
        assert {hit.persona_id for hit in match.hits} == {match.persona_id}


async def test_the_minimum_similarity_filters_weak_matches(fake_search: KnowledgeSearch) -> None:
    # The fake embedder gives the same vector to the same text: similarity 1 for QUALITY.
    everyone = await fake_search.search_other_personas(JUAN, QUALITY)
    assert {match.persona_id for match in everyone} == {ANA, PEDRO}
    assert everyone[0].persona_id == ANA
    assert everyone[0].similarity == pytest.approx(1.0)

    strong = await fake_search.search_other_personas(JUAN, QUALITY, min_similarity=0.99)
    assert [match.persona_id for match in strong] == [ANA]
