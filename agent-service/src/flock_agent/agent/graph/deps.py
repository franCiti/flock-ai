"""What the nodes need besides the state: models, search, messages and parameters (plan 4.3)."""

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from flock_agent.agent.messages import Messages
from flock_agent.knowledge.models import PersonaMatch, SearchHit


class Searcher(Protocol):
    """The hybrid search (knowledge.search.KnowledgeSearch), always filtered by persona."""

    async def search(self, persona_id: str, query: str) -> list[SearchHit]: ...

    async def search_other_personas(
        self, persona_id: str, query: str, *, min_similarity: float | None = None
    ) -> list[PersonaMatch]: ...


@dataclass(frozen=True)
class Dependencies:
    # Writes the answers, streaming (LLM_MODEL)
    main_model: BaseChatModel
    # Short structured calls and language adaptation (LLM_FAST_MODEL)
    fast_model: BaseChatModel
    search: Searcher
    messages: Messages
    # Conversation turns given to the LLM (HISTORY_TURNS)
    history_turns: int
    # Minimum similarity to suggest another persona (REFERRAL_MIN_SCORE; None = no threshold)
    referral_min_score: float | None = None
