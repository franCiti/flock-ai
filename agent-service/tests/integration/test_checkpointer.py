"""LangGraph checkpoints in PostgreSQL, schema `agent` (task T24, plan 3.3)."""

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from flock_agent.agent.fake_llm import FakeChatModel
from flock_agent.agent.graph.builder import build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.state import AgentState, PersonaRef, turn_input
from flock_agent.agent.messages import Messages
from flock_agent.common.db import Pool
from tests.fakes import FakeSearch
from tests.integration.containers import TestDatabase

pytestmark = pytest.mark.integration_containers

JUAN = PersonaRef(id="juan-plataforma", display_name="Juan Pérez")
THREAD: RunnableConfig = {"configurable": {"thread_id": "core-api:c1:0"}}


def small_talk() -> dict[str, Any]:
    return {
        "language": "es",
        "intent": "small_talk",
        "standalone_query": "Hola",
        "manipulation_attempt": False,
    }


def deps(fast: FakeChatModel) -> Dependencies:
    return Dependencies(
        main_model=FakeChatModel.scripted([]),
        fast_model=fast,
        search=FakeSearch(),
        messages=Messages(),
        history_turns=6,
    )


@pytest.fixture
async def saver(test_database: TestDatabase) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(
        test_database.conninfo("agent"), serde=checkpoint_serializer()
    ) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


async def test_checkpoint_tables_live_in_the_agent_schema(
    saver: AsyncPostgresSaver, agent_pool: Pool
) -> None:
    async with agent_pool.connection() as connection:
        cursor = await connection.execute("SELECT to_regclass('agent.checkpoints') IS NOT NULL")
        assert await cursor.fetchone() == (True,)


async def test_the_history_survives_a_new_saver(
    saver: AsyncPostgresSaver, test_database: TestDatabase
) -> None:
    await saver.adelete_thread("core-api:c1:0")
    first = build_graph(deps(FakeChatModel.scripted([small_talk()])), saver)
    await first.ainvoke(turn_input("Hola", JUAN, "cnry-a"), THREAD)

    # Another process (a restarted worker) reads the same conversation.
    async with AsyncPostgresSaver.from_conn_string(
        test_database.conninfo("agent"), serde=checkpoint_serializer()
    ) as other:
        fast = FakeChatModel.scripted([small_talk()])
        second = build_graph(deps(fast), other)
        result = cast(
            AgentState, await second.ainvoke(turn_input("Gracias", JUAN, "cnry-b"), THREAD)
        )
    assert [turn["question"] for turn in result["history"]] == ["Hola", "Gracias"]
    assert "User: Hola" in str(fast.calls[0][1].content)


async def test_deleting_a_thread_forgets_the_conversation(saver: AsyncPostgresSaver) -> None:
    graph = build_graph(deps(FakeChatModel.scripted([small_talk()])), saver)
    await graph.ainvoke(turn_input("Hola", JUAN, "cnry-a"), THREAD)
    await saver.adelete_thread("core-api:c1:0")
    state = await graph.aget_state(THREAD)
    assert state.values == {}
