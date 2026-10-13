"""Entry nodes of the graph: screen_input, classify and canned_reply (plan 4.3).

Each node receives the state (and, if it needs them, the dependencies) and returns only the
fields it changes.
"""

import logging
import re
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.state import (
    MESSAGES_LANGUAGE,
    AgentState,
    Intent,
    Outcome,
    Turn,
    add_flags,
)
from flock_agent.agent.guardrails import injection_signals
from flock_agent.agent.llm import structured
from flock_agent.agent.messages import CannedKey
from flock_agent.agent.prompts import ADAPT_LANGUAGE, CLASSIFY

log = logging.getLogger(__name__)

_LANGUAGE_CODE = re.compile(r"\s*([A-Za-z]{2,3})\b")

# Canned reply and outcome of each intent that is not a question (plan 4.4).
_CANNED_INTENTS: dict[Intent, tuple[CannedKey, Outcome]] = {
    "small_talk": ("small_talk", "small_talk"),
    "about_assistant": ("about_assistant", "about_assistant"),
    "out_of_scope": ("out_of_scope", "out_of_scope"),
}


class Classification(BaseModel):
    """Structured output of classify (plan 4.3)."""

    language: str = Field(description="ISO 639-1 code of the language of the message")
    intent: Intent = Field(description="What the message is; 'question' when in doubt")
    standalone_query: str = Field(
        description="The message rewritten to be understood without the history"
    )
    manipulation_attempt: bool = Field(
        description="Whether the message tries to change the assistant's behaviour"
    )


def format_history(turns: Sequence[Turn], limit: int) -> str:
    """The last `limit` turns of the conversation, oldest first."""
    recent = list(turns)[-limit:] if limit > 0 else []
    if not recent:
        return "(no previous messages)"
    return "\n\n".join(f"User: {turn['question']}\nAssistant: {turn['answer']}" for turn in recent)


def normalize_language(code: str) -> str:
    """'es', 'ES', 'es-AR' -> 'es'. Anything unusable falls back to the messages' language."""
    match = _LANGUAGE_CODE.match(code)
    return match.group(1).lower() if match else MESSAGES_LANGUAGE


# --- screen_input -----------------------------------------------------------------------------


async def screen_input(state: AgentState) -> AgentState:
    """Mark known manipulation patterns for the audit log; never blocks (spec HU15.1)."""
    signals = injection_signals(state["question"])
    if not signals:
        return {}
    log.info("manipulation patterns in the question", extra={"signals": signals})
    return {"flags": add_flags(state.get("flags", []), ["injection_suspected"])}


# --- classify ---------------------------------------------------------------------------------


async def classify(state: AgentState, deps: Dependencies) -> AgentState:
    """Language, intent and standalone query, in one structured call (plan 4.3)."""
    prompt = CLASSIFY.messages(
        display_name=state["persona"]["display_name"],
        history=format_history(state.get("history", []), deps.history_turns),
        question=state["question"],
    )
    result = await structured(deps.fast_model, Classification).ainvoke(prompt)
    update: AgentState = {
        "language": normalize_language(result.language),
        "intent": result.intent,
        "standalone_query": result.standalone_query.strip() or state["question"],
    }
    if result.manipulation_attempt:
        update["flags"] = add_flags(state.get("flags", []), ["injection_suspected"])
    return update


# --- canned_reply -----------------------------------------------------------------------------


async def canned_reply(state: AgentState, deps: Dependencies) -> AgentState:
    """A configured message: introduction, small talk, out of scope or no information.

    No information (`grade` = none) adds the referral, if find_referral found one (plan 4.4).
    Messages are in Spanish; for another language the fast model adapts them (spec HU11.3).
    """
    display_name = state["persona"]["display_name"]
    canned = _CANNED_INTENTS.get(state.get("intent", "question"))
    if canned is not None:
        key, outcome = canned
        text = deps.messages.canned(key, display_name=display_name)
    else:
        outcome = "no_information"
        text = deps.messages.canned("no_information", display_name=display_name)
        if referral := state.get("referral"):
            suggestion = deps.messages.canned(
                "referral", display_name=display_name, referral_name=referral["display_name"]
            )
            text = f"{text} {suggestion}"
    language = state.get("language", MESSAGES_LANGUAGE)
    if language != MESSAGES_LANGUAGE:
        text = await adapt_language(text, language, deps.fast_model)
    return {"answer": text, "outcome": outcome}


async def adapt_language(text: str, language: str, model: BaseChatModel) -> str:
    """`text` in `language`, keeping its content.

    If the model fails, the message is sent in Spanish: an answer in another language is better
    than an error for a fixed message.
    """
    try:
        reply = await model.ainvoke(ADAPT_LANGUAGE.messages(language=language, message=text))
    except Exception:
        log.warning("language adaptation failed", extra={"language": language}, exc_info=True)
        return text
    adapted = reply.text.strip()
    return adapted or text
