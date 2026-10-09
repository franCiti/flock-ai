"""Chat models through OpenRouter (D08, plan section 4.7).

Two roles: the main model writes the answers (`generate`, streaming) and the fast model does the
short structured calls (`classify`, `grade`, `find_referral`, language adaptation). Both are
OpenAI-compatible models reached through OpenRouter's URL.
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from flock_agent.common.settings import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter shows this name in its activity log.
_APP_HEADERS = {"X-Title": "flock-ai"}

# Structured calls are retried once on a transient error (plan 4.7). The graph timeout
# (ANSWER_TIMEOUT) bounds everything, retries included.
_MAX_RETRIES = 1


class LlmConfigError(ValueError):
    """The LLM settings are missing or incomplete."""


@dataclass(frozen=True)
class LlmModels:
    """The models of the agent and their names (recorded in the audit log, D08)."""

    main: BaseChatModel
    main_name: str
    fast: BaseChatModel
    fast_name: str


def openrouter_chat_model(settings: Settings, model: str) -> ChatOpenAI:
    if settings.openrouter_api_key is None:
        msg = "missing LLM setting: OPENROUTER_API_KEY"
        raise LlmConfigError(msg)
    return ChatOpenAI(
        model_name=model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        temperature=0,
        max_retries=_MAX_RETRIES,
        default_headers=_APP_HEADERS,
    )


def create_models(settings: Settings) -> LlmModels:
    """Main and fast models from LLM_MODEL and LLM_FAST_MODEL (defaults to the main one)."""
    main_name = settings.llm_model
    fast_name = settings.effective_fast_model
    if main_name is None or fast_name is None:
        msg = "missing LLM setting: LLM_MODEL"
        raise LlmConfigError(msg)
    return LlmModels(
        main=openrouter_chat_model(settings, main_name),
        main_name=main_name,
        fast=openrouter_chat_model(settings, fast_name),
        fast_name=fast_name,
    )


def structured[T: BaseModel](
    model: BaseChatModel, schema: type[T]
) -> Runnable[LanguageModelInput, T]:
    """The model answering with an instance of `schema`, validated.

    Uses tool calling: it is what OpenRouter supports for most models (D08 requires it), while
    native JSON schema output depends on the provider.
    """
    runnable: Runnable[LanguageModelInput, Any] = model.with_structured_output(
        schema, method="function_calling"
    )
    return runnable
