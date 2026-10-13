"""State of the agent's graph (plan 4.2).

Every node receives the whole state and returns only the fields it changes. All fields are
optional for the type checker.

The checkpointer keeps the state of each conversation between questions, but only `history`
must carry over: every question starts from `turn_input`, which resets the other fields.
"""

from typing import Literal, TypedDict

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


class CitationRef(TypedDict):
    """A source of the answer, as the `citations` of the final reply (plan 2.4)."""

    document_id: str
    title: str
    url: str | None
    path: str | None
    section: str | None
    source_type: str


def add_flags(current: list[Flag], new: list[Flag]) -> list[Flag]:
    """Flags accumulate across the nodes of one question, without repeats and in a stable order.

    Nodes merge them themselves (they run one after the other) instead of a LangGraph reducer:
    a reducer would also merge them across questions, and they belong to one question only.
    """
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
    # Answer (finalize)
    answer: str
    outcome: Outcome
    citations: list[CitationRef]
    flags: list[Flag]


def turn_input(question: str, persona: PersonaRef, canary: str) -> AgentState:
    """Input of the graph for one question: the question plus every per-question field reset.

    `history` is left out, so the conversation's history (from the checkpointer) is kept.
    """
    return {
        "question": question,
        "persona": persona,
        "canary": canary,
        "language": MESSAGES_LANGUAGE,
        "intent": "question",
        "standalone_query": question,
        "hits": [],
        "verdict": "none",
        "missing": "",
        "referral": None,
        "answer": "",
        "outcome": "no_information",
        "citations": [],
        "flags": [],
    }
