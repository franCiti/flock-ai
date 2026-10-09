"""What the nodes need besides the state: models, messages and parameters (plan 4.3, 4.7)."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from flock_agent.agent.messages import Messages


@dataclass(frozen=True)
class Dependencies:
    # Short structured calls and language adaptation (LLM_FAST_MODEL)
    fast_model: BaseChatModel
    messages: Messages
    # Conversation turns given to classify (HISTORY_TURNS)
    history_turns: int
