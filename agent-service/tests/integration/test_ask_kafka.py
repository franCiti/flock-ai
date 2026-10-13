"""flock-ask against the Agent Worker over Kafka, with the development fake LLM (task T26)."""

import io
from collections.abc import AsyncIterator, Iterator

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from flock_agent.agent.fake_llm import development_model
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.messages import Messages
from flock_agent.common.db import Pool
from flock_agent.knowledge.models import Persona, SearchHit
from flock_agent.knowledge.repository import KnowledgeRepository
from flock_agent.tools.ask import AskSession
from tests.fakes import FakeSearch
from tests.integration.containers import running_kafka
from tests.integration.kafka_agent import RunningWorker, Topics

pytestmark = pytest.mark.integration_containers

ROLLBACK = SearchHit(
    chunk_id=1,
    persona_id="juan-plataforma",
    document_id="file:juan-plataforma:deploy.md",
    source_type="file",
    title="deploy.md",
    url=None,
    path="procedimientos/deploy.md",
    section_hint=None,
    heading_path="Rollback",
    content="[deploy.md > Rollback]\nPara hacer rollback, ejecutá el job rollback-prod.",
    similarity=0.8,
    score=0.01,
)


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    with running_kafka() as bootstrap:
        yield bootstrap


@pytest.fixture
async def worker(
    kafka: str, knowledge: KnowledgeRepository, agent_tables: Pool
) -> AsyncIterator[RunningWorker]:
    await knowledge.upsert_persona(
        Persona(id="juan-plataforma", display_name="Juan Pérez", profile_hash="h")
    )
    topics = await Topics().create(kafka)
    deps = Dependencies(
        main_model=development_model(),
        fast_model=development_model(),
        search=FakeSearch(hits=[ROLLBACK]),
        messages=Messages(),
        history_turns=6,
    )
    async with RunningWorker(kafka, topics, agent_tables, deps) as running:
        yield running


@pytest.fixture
async def session(
    kafka: str, worker: RunningWorker
) -> AsyncIterator[tuple[AskSession, io.StringIO]]:
    producer = AIOKafkaProducer(bootstrap_servers=kafka)
    consumer = AIOKafkaConsumer(worker.topics.app_a, bootstrap_servers=kafka)
    await producer.start()
    await consumer.start()
    out = io.StringIO()
    ask = AskSession(
        producer,
        consumer,
        persona_id="juan-plataforma",
        conversation_id="cli-test",
        out=out,
        requests_topic=worker.topics.requests,
        reply_topic=worker.topics.app_a,
    )
    await ask.ready()
    try:
        yield ask, out
    finally:
        await consumer.stop()
        await producer.stop()


async def test_a_question_shows_the_answer_and_its_sources(
    session: tuple[AskSession, io.StringIO],
) -> None:
    ask, out = session
    assert await ask.ask("¿Cómo hago rollback?") == 0
    text = out.getvalue()
    assert "[deploy.md > Rollback] Para hacer rollback, ejecutá el job rollback-prod. [1]" in text
    assert "Sources:\n  [1] deploy.md > Rollback (procedimientos/deploy.md)" in text
    assert "[answered · Juan Pérez" in text


async def test_a_conversation_keeps_going(session: tuple[AskSession, io.StringIO]) -> None:
    ask, out = session
    assert await ask.ask("Hola") == 0
    assert await ask.ask("¿Quién sos?") == 0
    text = out.getvalue()
    assert "[small_talk · Juan Pérez" in text
    assert "[about_assistant · Juan Pérez" in text
    assert "no soy Juan Pérez" in text


async def test_an_unknown_persona_is_an_error(
    kafka: str, worker: RunningWorker, session: tuple[AskSession, io.StringIO]
) -> None:
    ask, out = session
    other = AskSession(
        ask._producer,  # same clients, another persona
        ask._consumer,
        persona_id="nadie",
        conversation_id="cli-test-2",
        out=out,
        requests_topic=worker.topics.requests,
        reply_topic=worker.topics.app_a,
    )
    assert await other.ask("Hola") == 1
    assert "Error PERSONA_NOT_FOUND" in out.getvalue()
