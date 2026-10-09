"""System prompts, in English and versioned (plan 4.6)."""

from flock_agent.agent.prompts.base import Prompt, contains_canary, new_canary, prompt_version
from flock_agent.agent.prompts.templates import (
    ADAPT_LANGUAGE,
    ALL_PROMPTS,
    CLASSIFY,
    CONFIRM_REFERRAL,
    GENERATE,
    GRADE,
)

# Recorded in the audit log next to the model (D08).
PROMPT_VERSION = prompt_version(ALL_PROMPTS)

__all__ = [
    "ADAPT_LANGUAGE",
    "ALL_PROMPTS",
    "CLASSIFY",
    "CONFIRM_REFERRAL",
    "GENERATE",
    "GRADE",
    "PROMPT_VERSION",
    "Prompt",
    "contains_canary",
    "new_canary",
    "prompt_version",
]
