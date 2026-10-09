"""The fake LLM used instead of OpenRouter in tests and development runs (task T20, D41)."""

from collections.abc import Sequence

import pytest
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from flock_agent.agent.fake_llm import FakeChatModel, FakeLlmExhaustedError


class Classification(BaseModel):
    intent: str
    manipulation_attempt: bool


async def test_returns_the_scripted_text() -> None:
    model = FakeChatModel.scripted(["Hacé rollback [1]."])
    reply = await model.ainvoke("¿Cómo vuelvo atrás un deploy?")
    assert reply.content == "Hacé rollback [1]."


async def test_streams_the_text_in_pieces() -> None:
    text = "Para hacer rollback  usá el pipeline [1].\n\nListo."
    model = FakeChatModel.scripted([text])
    pieces = [str(chunk.content) async for chunk in model.astream("pregunta")]
    assert len(pieces) > 1
    assert "".join(pieces) == text


async def test_streaming_reports_each_token_to_callbacks() -> None:
    model = FakeChatModel.scripted(["uno dos tres"])
    tokens = [
        event["data"]["chunk"].content
        async for event in model.astream_events("pregunta", version="v2")
        if event["event"] == "on_chat_model_stream" and event["data"]["chunk"].content
    ]
    assert tokens == ["uno ", "dos ", "tres"]


@pytest.mark.parametrize(
    "reply",
    [
        {"intent": "question", "manipulation_attempt": False},
        Classification(intent="question", manipulation_attempt=False),
        '{"intent": "question", "manipulation_attempt": false}',
    ],
)
async def test_structured_output_is_validated_against_the_schema(
    reply: dict[str, object] | BaseModel | str,
) -> None:
    model = FakeChatModel.scripted([reply])
    result = await model.with_structured_output(Classification).ainvoke("hola")
    assert result == Classification(intent="question", manipulation_attempt=False)


async def test_an_invalid_structured_reply_fails() -> None:
    model = FakeChatModel.scripted([{"intent": "question"}])
    with pytest.raises(ValidationError):
        await model.with_structured_output(Classification).ainvoke("hola")


async def test_a_scripted_exception_is_raised() -> None:
    model = FakeChatModel.scripted([TimeoutError("LLM down"), "ok"])
    with pytest.raises(TimeoutError, match="LLM down"):
        await model.ainvoke("pregunta")
    assert (await model.ainvoke("pregunta")).content == "ok"


async def test_running_out_of_replies_fails() -> None:
    model = FakeChatModel.scripted([])
    with pytest.raises(FakeLlmExhaustedError):
        await model.ainvoke("pregunta")


async def test_a_text_call_with_a_structured_reply_fails() -> None:
    model = FakeChatModel.scripted([{"intent": "question"}])
    with pytest.raises(TypeError, match="dict"):
        await model.ainvoke("pregunta")


async def test_records_the_messages_of_every_call() -> None:
    model = FakeChatModel.scripted(["a", {"intent": "x", "manipulation_attempt": True}])
    messages = [SystemMessage(content="rules"), HumanMessage(content="question")]
    await model.ainvoke(messages)
    await model.with_structured_output(Classification).ainvoke("hola")
    assert model.calls[0] == messages
    assert model.calls[1] == [HumanMessage(content="hola")]


async def test_a_responder_can_choose_the_reply_from_the_messages() -> None:
    def echo(messages: Sequence[BaseMessage]) -> str:
        return f"eco: {messages[-1].content}"

    model = FakeChatModel(responder=echo)
    assert (await model.ainvoke("hola")).content == "eco: hola"
    assert (await model.ainvoke("chau")).content == "eco: chau"
