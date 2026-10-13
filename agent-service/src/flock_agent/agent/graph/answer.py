"""Answer nodes of the graph: retrieve, grade, generate and find_referral (plan 4.3).

The persona's fragments only reach the LLM inside <document> delimiters, and generate only sees
the ones grade found relevant. Another persona's fragments are used to decide a referral, never
to write the answer (spec HU2.3, HU15.3).
"""

import logging
from collections.abc import Sequence
from html import escape

from pydantic import BaseModel, Field

from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.entry import adapt_language, format_history
from flock_agent.agent.graph.state import (
    MESSAGES_LANGUAGE,
    AgentState,
    Outcome,
    Referral,
    Verdict,
)
from flock_agent.agent.llm import structured
from flock_agent.agent.prompts import CONFIRM_REFERRAL, GENERATE, GRADE
from flock_agent.knowledge.models import SearchHit

log = logging.getLogger(__name__)

# Tag of the LLM call whose tokens are the answer: the worker streams only those (D11, T25).
ANSWER_STREAM_TAG = "answer_stream"

# Fragments of the other persona shown to the LLM to confirm a referral.
_REFERRAL_EVIDENCE = 3


class Grade(BaseModel):
    """Structured output of grade (plan 4.3)."""

    verdict: Verdict = Field(description="Whether the excerpts answer the question")
    relevant_ids: list[int] = Field(
        default_factory=list, description="Ids of the excerpts that help answer the question"
    )
    missing: str = Field(default="", description="The part not covered, if the verdict is partial")


class ReferralCheck(BaseModel):
    """Structured output of the referral confirmation (plan 4.3 find_referral)."""

    answers: bool = Field(description="Whether the excerpts answer the question")


def format_documents(hits: Sequence[SearchHit]) -> str:
    """The fragments numbered from 1, each inside its own delimiter.

    The text is escaped so a fragment cannot close its delimiter or open a fake one
    (spec HU15.2): "</document>" inside a document becomes "&lt;/document&gt;".
    """
    return "\n\n".join(
        f'<document id="{number}" title="{escape(hit.title)}">\n'
        f"{escape(hit.content, quote=False)}\n</document>"
        for number, hit in enumerate(hits, start=1)
    )


# --- retrieve ---------------------------------------------------------------------------------


async def retrieve(state: AgentState, deps: Dependencies) -> AgentState:
    """Hybrid search in the fragments of this persona only (spec HU3)."""
    query = state.get("standalone_query") or state["question"]
    return {"hits": await deps.search.search(state["persona"]["id"], query)}


# --- grade ------------------------------------------------------------------------------------


async def grade(state: AgentState, deps: Dependencies) -> AgentState:
    """Whether the fragments answer the question; keeps only the relevant ones."""
    hits = state.get("hits", [])
    if not hits:
        return {"verdict": "none", "missing": "", "hits": []}
    prompt = GRADE.messages(
        display_name=state["persona"]["display_name"],
        language=state.get("language", MESSAGES_LANGUAGE),
        question=state.get("standalone_query") or state["question"],
        documents=format_documents(hits),
    )
    result = await structured(deps.fast_model, Grade).ainvoke(prompt)
    if result.verdict == "none":
        return {"verdict": "none", "missing": "", "hits": []}
    relevant = [hits[i - 1] for i in dict.fromkeys(result.relevant_ids) if 1 <= i <= len(hits)]
    missing = result.missing.strip() if result.verdict == "partial" else ""
    # An answer without relevant fragments is inconsistent: generate gets them all rather than
    # none, and its citations still point to real fragments.
    return {"verdict": result.verdict, "missing": missing, "hits": relevant or list(hits)}


# --- generate ---------------------------------------------------------------------------------


async def generate(state: AgentState, deps: Dependencies) -> AgentState:
    """The answer from the relevant fragments, streaming (spec HU1, HU2.5, HU6).

    If the verdict was partial, the answer says what it did not find and, if find_referral
    found someone, ends with the suggestion (plan 4.3).
    """
    language = state.get("language", MESSAGES_LANGUAGE)
    prompt = GENERATE.messages(
        display_name=state["persona"]["display_name"],
        language=language,
        canary=state["canary"],
        history=format_history(state.get("history", []), deps.history_turns),
        documents=format_documents(state.get("hits", [])),
        missing=state.get("missing", ""),
        question=state["question"],
    )
    model = deps.main_model.with_config(tags=[ANSWER_STREAM_TAG])
    parts = [chunk.text async for chunk in model.astream(prompt)]
    answer = "".join(parts).strip()
    if referral := state.get("referral"):
        suggestion = deps.messages.canned(
            "referral",
            display_name=state["persona"]["display_name"],
            referral_name=referral["display_name"],
        )
        if language != MESSAGES_LANGUAGE:
            suggestion = await adapt_language(suggestion, language, deps.fast_model)
        answer = f"{answer}\n\n{suggestion}"
    outcome: Outcome = "answered" if state.get("verdict") == "sufficient" else "partially_answered"
    return {"answer": answer, "outcome": outcome}


# --- find_referral ----------------------------------------------------------------------------


async def find_referral(state: AgentState, deps: Dependencies) -> AgentState:
    """Another persona who may know the answer, or the part that is missing (spec HU2).

    Only the referral leaves this node: the other persona's fragments go to the confirmation
    call and nowhere else. If the confirmation fails, there is no referral: it is a suggestion,
    not worth failing the answer for.
    """
    question = state.get("standalone_query") or state["question"]
    query = state.get("missing") or question
    matches = await deps.search.search_other_personas(
        state["persona"]["id"], query, min_similarity=deps.referral_min_score
    )
    if not matches:
        return {"referral": None}
    best = matches[0]
    prompt = CONFIRM_REFERRAL.messages(
        question=query, documents=format_documents(best.hits[:_REFERRAL_EVIDENCE])
    )
    try:
        check = await structured(deps.fast_model, ReferralCheck).ainvoke(prompt)
    except Exception:
        log.warning(
            "referral confirmation failed", extra={"candidate": best.persona_id}, exc_info=True
        )
        return {"referral": None}
    if not check.answers:
        return {"referral": None}
    return {"referral": Referral(persona_id=best.persona_id, display_name=best.display_name)}
