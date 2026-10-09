"""State of the agent's graph (plan 4.2).

Every node receives the whole state and returns only the fields it changes. All fields are
optional for the type checker; the worker sets the input fields before running the graph.
"""

from typing import Annotated, Literal, TypedDict

from flock_agent.knowledge.models import SearchHit

Intent = Literal["question", "small_talk", "about_assistant", "out_of_scope"]
Verdict = Literal["sufficient", "partial", "none"]
Outcome = Literal[
    "answered",
    "partially_answered",
    "no_information",
    "out_of_scope",
    "small_talk",
    "about_assistant",
]
Flag = Literal["injection_suspected", "rate_limited", "question_too_long", "invalid_request"]

# Language of the configured messages (spec HU11.3): canned replies in it need no adaptation.
MESSAGES_LANGUAGE = "es"


class Turn(TypedDict):
    """One exchange of the conversation history (never the fragments, plan 4.3 `finalize`)."""

    question: str
    answer: str


class PersonaRef(TypedDict):
    id: str
    display_name: str


class Referral(TypedDict):
    persona_id: str
    display_name: str


def add_flags(current: list[Flag], new: list[Flag]) -> list[Flag]:
    """Flags accumulate across nodes, without repeats and in a stable order."""
    return sorted(set(current) | set(new))


class AgentState(TypedDict, total=False):
    # Input, set by the worker
    question: str
    persona: PersonaRef
    canary: str  # secret of this request's system prompt (plan 4.5)
    history: list[Turn]
    # classify
    language: str  # ISO 639-1 code of the question
    intent: Intent
    standalone_query: str
    # retrieve, grade, find_referral (T23)
    hits: list[SearchHit]
    verdict: Verdict
    missing: str
    referral: Referral | None
    # Answer
    answer: str
    outcome: Outcome
    flags: Annotated[list[Flag], add_flags]
