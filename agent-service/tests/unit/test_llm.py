"""OpenRouter chat model factory (task T20, plan 4.7, D08). No network: models are only built."""

import pytest
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from flock_agent.agent.fake_llm import FakeChatModel
from flock_agent.agent.llm import OPENROUTER_BASE_URL, LlmConfigError, create_models, structured
from flock_agent.common.settings import Settings


def make_settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_models_point_to_openrouter() -> None:
    models = create_models(
        make_settings(openrouter_api_key="test-key", llm_model="main/m", llm_fast_model="fast/m")
    )
    assert (models.main_name, models.fast_name) == ("main/m", "fast/m")
    for model, name in ((models.main, "main/m"), (models.fast, "fast/m")):
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == name
        assert model.openai_api_base == OPENROUTER_BASE_URL
        assert isinstance(model.openai_api_key, SecretStr)
        assert model.openai_api_key.get_secret_value() == "test-key"
        assert model.temperature == 0
        assert model.max_retries == 1


def test_the_fast_model_defaults_to_the_main_one() -> None:
    models = create_models(make_settings(openrouter_api_key="test-key", llm_model="main/m"))
    assert models.fast_name == "main/m"


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({"llm_model": "main/m"}, "OPENROUTER_API_KEY"),
        ({"openrouter_api_key": "test-key"}, "LLM_MODEL"),
    ],
)
def test_missing_settings_are_reported(env: dict[str, str], missing: str) -> None:
    with pytest.raises(LlmConfigError, match=missing):
        create_models(make_settings(**env))


class Verdict(BaseModel):
    verdict: str


async def test_structured_returns_the_schema() -> None:
    model = FakeChatModel.scripted([{"verdict": "none"}])
    assert await structured(model, Verdict).ainvoke("question") == Verdict(verdict="none")
