"""A fake chat model that returns predefined replies (plan 8.1, D41).

It stands in for OpenRouter wherever the real model must not be used: the tests, and the
end-to-end runs during development (flock-ask and flock-eval against the containers, T27 and
T28), so no API key is needed and the results are always the same.

A reply is chosen by a `responder` that receives the messages sent to the model:
- a `str` is a text reply (streamed word by word);
- a pydantic model or a dict is a structured reply (`with_structured_output`);
- an exception is raised, to simulate a failing LLM.

`delay` makes every asynchronous call wait that many seconds first, to simulate a slow model.
"""

import asyncio
import html
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

from flock_agent.agent.prompts import (
    ADAPT_LANGUAGE,
    CLASSIFY,
    CONFIRM_REFERRAL,
    GENERATE,
    GRADE,
    JUDGE,
    Prompt,
)

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
    # Seconds each asynchronous call waits before replying (a slow model).
    delay: float = 0.0

    @classmethod
    def scripted(cls, replies: Iterable[FakeReply], *, delay: float = 0.0) -> "FakeChatModel":
        """A fake model that returns `replies` in order, one per call."""
        queue = deque(replies)

        def next_reply(_messages: Sequence[BaseMessage]) -> FakeReply:
            if not queue:
                msg = "the fake LLM has no more scripted replies"
                raise FakeLlmExhaustedError(msg)
            return queue.popleft()

        return cls(responder=next_reply, delay=delay)

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

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        await asyncio.sleep(self.delay)
        return self._generate(messages)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        await asyncio.sleep(self.delay)
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
            await asyncio.sleep(self.delay)
            return parse(model_input)

        return RunnableLambda(parse, afunc=aparse)


# --- Development model --------------------------------------------------------------------------

_BLOCK = r"<{tag}>\n(.*?)\n</{tag}>"
_DOCUMENT = re.compile(r'<document id="(\d+)"[^>]*>\n(.*?)\n</document>', re.DOTALL)
_GREETING = re.compile(
    r"^\W*(hola|buen[oa]s|gracias|chau|adi[oó]s|hello|hi|thanks|thank you|bye)\b", re.IGNORECASE
)
_ABOUT = re.compile(r"qui[eé]n sos|qui[eé]n eres|who are you|qu[eé] sab[eé]s hacer", re.IGNORECASE)
_EXCERPT_CHARS = 300


def _block(text: str, tag: str) -> str:
    match = re.search(_BLOCK.format(tag=tag), text, re.DOTALL)
    return "" if match is None else match.group(1).strip()


def development_reply(messages: Sequence[BaseMessage]) -> FakeReply:
    """A plausible reply for each prompt of the agent, without any real model (D41).

    It lets the whole system run end to end (flock-ask, flock-eval, Docker Compose) with
    LLM_PROVIDER=fake: greetings are small talk, "who are you" questions are about the
    assistant, everything else is a question answered with the first fragment found.
    """
    system = str(messages[0].content) if messages else ""
    human = str(messages[-1].content) if messages else ""

    def is_prompt(prompt: Prompt) -> bool:
        return system.startswith(prompt.system.split("{", 1)[0])

    if is_prompt(CLASSIFY):
        question = _block(human, "message")
        intent = (
            "small_talk"
            if _GREETING.match(question)
            else "about_assistant"
            if _ABOUT.search(question)
            else "question"
        )
        return {
            "language": "es",
            "intent": intent,
            "standalone_query": question,
            "manipulation_attempt": False,
        }
    documents = _DOCUMENT.findall(human)
    if is_prompt(GRADE):
        ids = [int(number) for number, _ in documents]
        return {"verdict": "sufficient" if ids else "none", "relevant_ids": ids, "missing": ""}
    if is_prompt(CONFIRM_REFERRAL):
        return {"answers": bool(documents)}
    if is_prompt(GENERATE):
        if not documents:
            return "No encontré información sobre eso."
        # Fragments reach the prompt escaped (graph.answer.format_documents).
        excerpt = " ".join(html.unescape(documents[0][1]).split())[:_EXCERPT_CHARS]
        return f"Según la documentación: {excerpt} [1]"
    if is_prompt(ADAPT_LANGUAGE):
        return _block(human, "message")
    if is_prompt(JUDGE):
        return _judge(human)
    return "OK"


_WORD = re.compile(r"\w{4,}")
_MIN_FACT_WORDS_FOUND = 0.6


def _judge(human: str) -> dict[str, Any]:
    """A fact is present if most of its words (4 letters or more) appear in the answer."""
    answer = set(_WORD.findall(_block(human, "answer").lower()))
    verdicts = []
    for line in _block(human, "facts").splitlines():
        fact = line.removeprefix("- ").strip()
        words = _WORD.findall(fact.lower())
        found = sum(word in answer for word in words)
        present = bool(words) and found / len(words) >= _MIN_FACT_WORDS_FOUND
        verdicts.append(
            {
                "fact": fact,
                "present": present,
                "explanation": f"{found} of {len(words)} words of the fact are in the answer",
            }
        )
    return {"facts": verdicts}


def development_model() -> FakeChatModel:
    return FakeChatModel(responder=development_reply)
