"""The development fake model (LLM_PROVIDER=fake): the whole graph runs without an API key."""

from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from flock_agent.agent.fake_llm import FakeChatModel, development_model
from flock_agent.agent.graph.builder import build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.state import AgentState, PersonaRef, turn_input
from flock_agent.agent.llm import create_models
from flock_agent.agent.messages import Messages
from flock_agent.common.settings import Settings
from flock_agent.knowledge.models import SearchHit
from tests.fakes import FakeSearch

JUAN = PersonaRef(id="juan-plataforma", display_name="Juan Pérez")
ROLLBACK = SearchHit(
    chunk_id=1,
    persona_id="juan-plataforma",
    document_id="file:juan-plataforma:deploy.md",
    source_type="file",
    title="deploy.md",
    url=None,
    path="deploy.md",
    section_hint=None,
    heading_path="Rollback",
    content="[deploy.md > Rollback]\nPara hacer rollback, ejecutá el job rollback-prod.",
    similarity=0.8,
    score=0.01,
)


async def ask(question: str, search: FakeSearch) -> AgentState:
    deps = Dependencies(
        main_model=development_model(),
        fast_model=development_model(),
        search=search,
        messages=Messages(),
        history_turns=6,
    )
    graph = build_graph(deps, InMemorySaver(serde=checkpoint_serializer()))
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    return cast(AgentState, await graph.ainvoke(turn_input(question, JUAN, "cnry-x"), config))


async def test_a_question_is_answered_with_the_first_fragment() -> None:
    result = await ask("¿Cómo hago rollback?", FakeSearch(hits=[ROLLBACK]))
    assert result["outcome"] == "answered"
    assert "rollback-prod" in result["answer"]
    assert result["answer"].endswith("[1]")
    assert [c["document_id"] for c in result["citations"]] == [ROLLBACK.document_id]


async def test_greetings_and_introductions() -> None:
    assert (await ask("Hola!", FakeSearch()))["outcome"] == "small_talk"
    assert (await ask("¿Quién sos?", FakeSearch()))["outcome"] == "about_assistant"


async def test_without_fragments_there_is_no_information() -> None:
    assert (await ask("¿Qué es Kubernetes?", FakeSearch()))["outcome"] == "no_information"


def test_the_fake_provider_needs_no_api_key() -> None:
    models = create_models(Settings(_env_file=None, llm_provider="fake"))
    assert (models.main_name, models.fast_name) == ("fake", "fake")
    assert isinstance(models.main, FakeChatModel)
