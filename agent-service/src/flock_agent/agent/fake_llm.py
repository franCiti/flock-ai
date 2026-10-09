"""A fake chat model that returns predefined replies (plan 8.1, D41).

It stands in for OpenRouter wherever the real model must not be used: the tests, and the
end-to-end runs during development (flock-ask and flock-eval against the containers, T27 and
T28), so no API key is needed and the results are always the same.

A reply is chosen by a `responder` that receives the messages sent to the model:
- a `str` is a text reply (streamed word by word);
- a pydantic model or a dict is a structured reply (`with_structured_output`);
- an exception is raised, to simulate a failing LLM.
"""

import json
import re
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field

FakeReply = str | BaseModel | dict[str, Any] | Exception
Responder = Callable[[Sequence[BaseMessage]], FakeReply]

# Words with their trailing spaces: joining the pieces gives back the original text.
_STREAM_PIECES = re.compile(r"\S+\s*|\s+")


class FakeLlmExhaustedError(RuntimeError):
    """A scripted fake model was called more times than it has replies."""


class FakeChatModel(BaseChatModel):
    responder: Responder
    # Messages of every call, in order, for the tests to inspect.
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @classmethod
    def scripted(cls, replies: Iterable[FakeReply]) -> "FakeChatModel":
        """A fake model that returns `replies` in order, one per call."""
        queue = deque(replies)

        def next_reply(_messages: Sequence[BaseMessage]) -> FakeReply:
            if not queue:
                msg = "the fake LLM has no more scripted replies"
                raise FakeLlmExhaustedError(msg)
            return queue.popleft()

        return cls(responder=next_reply)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _reply(self, messages: Sequence[BaseMessage]) -> str | BaseModel | dict[str, Any]:
        self.calls.append(list(messages))
        reply = self.responder(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def _text_reply(self, messages: Sequence[BaseMessage]) -> str:
        reply = self._reply(messages)
        if not isinstance(reply, str):
            msg = f"the fake LLM got a text call but its reply is {type(reply).__name__}"
            raise TypeError(msg)
        return reply

    # --- Text and streaming -------------------------------------------------------------------

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self._text_reply(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        for piece in _STREAM_PIECES.findall(self._text_reply(messages)):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager is not None:
                run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for piece in _STREAM_PIECES.findall(self._text_reply(messages)):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager is not None:
                await run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk

    # --- Structured output --------------------------------------------------------------------

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        """Return the next reply validated against `schema` (method and other options ignored)."""
        if include_raw:
            msg = "the fake LLM does not support include_raw"
            raise NotImplementedError(msg)

        def parse(model_input: LanguageModelInput) -> dict[str, Any] | BaseModel:
            reply = self._reply(self._convert_input(model_input).to_messages())
            data = (
                reply.model_dump()
                if isinstance(reply, BaseModel)
                else json.loads(reply)
                if isinstance(reply, str)
                else reply
            )
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_validate(data)
            return dict(data)

        async def aparse(model_input: LanguageModelInput) -> dict[str, Any] | BaseModel:
            return parse(model_input)

        return RunnableLambda(parse, afunc=aparse)
