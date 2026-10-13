"""Assembly of the agent's graph (plan 4.2) and the serializer of its checkpoints (plan 3.3).

    START -> screen_input -> classify -> question?  -> retrieve -> grade
                                      -> otherwise  -> canned_reply
    grade -> sufficient     -> generate
          -> partial / none -> find_referral -> partial -> generate
                                             -> none    -> canned_reply
    generate, canned_reply -> finalize -> END

Each conversation is a LangGraph thread (`conversations.thread_id`); the checkpointer keeps its
history between questions.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from flock_agent.agent.graph.answer import find_referral, generate, grade, retrieve
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.entry import canned_reply, classify, screen_input
from flock_agent.agent.graph.finalize import finalize
from flock_agent.agent.graph.state import AgentState

Graph = CompiledStateGraph[AgentState, None, AgentState, AgentState]
Node = Callable[[AgentState, Dependencies], Awaitable[AgentState]]


class BoundNode(Protocol):
    """A node with its dependencies bound: what LangGraph calls (its parameter is `state`)."""

    def __call__(self, state: AgentState) -> Awaitable[AgentState]: ...


def checkpoint_serializer() -> JsonPlusSerializer:
    """Serializer of the checkpoints that accepts only our own types besides the standard ones.

    LangGraph will refuse to load types that are not listed (an untrusted checkpoint could
    otherwise build arbitrary objects).
    """
    return JsonPlusSerializer(
        allowed_msgpack_modules=[("flock_agent.knowledge.models", "SearchHit")]
    )


def route_intent(state: AgentState) -> str:
    return "retrieve" if state.get("intent", "question") == "question" else "canned_reply"


def route_verdict(state: AgentState) -> str:
    return "generate" if state.get("verdict") == "sufficient" else "find_referral"


def route_referral(state: AgentState) -> str:
    return "generate" if state.get("verdict") == "partial" else "canned_reply"


def build_graph(deps: Dependencies, checkpointer: BaseCheckpointSaver[Any] | None) -> Graph:
    def bind(node: Node) -> BoundNode:
        async def run(state: AgentState) -> AgentState:
            return await node(state, deps)

        return run

    builder = StateGraph(AgentState)
    builder.add_node("screen_input", screen_input)
    for name, node in (
        ("classify", classify),
        ("canned_reply", canned_reply),
        ("retrieve", retrieve),
        ("grade", grade),
        ("find_referral", find_referral),
        ("generate", generate),
        ("finalize", finalize),
    ):
        builder.add_node(name, bind(node))
    builder.add_edge(START, "screen_input")
    builder.add_edge("screen_input", "classify")
    builder.add_conditional_edges("classify", route_intent, ["retrieve", "canned_reply"])
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges("grade", route_verdict, ["generate", "find_referral"])
    builder.add_conditional_edges("find_referral", route_referral, ["generate", "canned_reply"])
    builder.add_edge("generate", "finalize")
    builder.add_edge("canned_reply", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
