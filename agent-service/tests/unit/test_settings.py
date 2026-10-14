from datetime import timedelta

import pytest
from pydantic import ValidationError

from flock_agent.common.settings import Settings


def make_settings(**env: str) -> Settings:
    """Build settings from the given values only, ignoring any real .env file."""
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_defaults_match_the_plan() -> None:
    settings = make_settings()

    assert settings.conversation_ttl == timedelta(days=1)
    assert settings.answer_timeout == timedelta(minutes=2)
    assert settings.first_token_target == timedelta(seconds=10)
    assert settings.max_question_chars == 2000
    assert settings.max_requests_per_minute == 30
    assert settings.retrieval_candidates == 20
    assert settings.retrieval_top_k == 8
    assert settings.history_turns == 6
    assert settings.referral_min_score == 0.40
    assert settings.max_file_mb == 20
    assert settings.openrouter_api_key is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("45s", timedelta(seconds=45)),
        ("2m", timedelta(minutes=2)),
        ("3h", timedelta(hours=3)),
        ("1d", timedelta(days=1)),
        (" 30m ", timedelta(minutes=30)),
    ],
)
def test_parses_compact_durations(raw: str, expected: timedelta) -> None:
    assert make_settings(answer_timeout=raw).answer_timeout == expected


@pytest.mark.parametrize("raw", ["2", "2 minutes", "m2", "-1m", "1.5m"])
def test_rejects_malformed_durations(raw: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(answer_timeout=raw)


def test_rejects_zero_duration() -> None:
    with pytest.raises(ValidationError):
        make_settings(conversation_ttl="0s")


def test_rejects_non_positive_limits() -> None:
    with pytest.raises(ValidationError):
        make_settings(max_question_chars="0")


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_QUESTION_CHARS", "500")
    monkeypatch.setenv("LLM_MODEL", "provider/model-a")

    settings = Settings(_env_file=None)

    assert settings.max_question_chars == 500
    assert settings.llm_model == "provider/model-a"


def test_empty_environment_variables_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("ANSWER_TIMEOUT", "")

    settings = Settings(_env_file=None)

    assert settings.llm_model is None
    assert settings.answer_timeout == timedelta(minutes=2)


def test_fast_model_defaults_to_main_model() -> None:
    assert make_settings(llm_model="a").effective_fast_model == "a"
    assert make_settings(llm_model="a", llm_fast_model="b").effective_fast_model == "b"


def test_api_key_is_not_printed() -> None:
    settings = make_settings(openrouter_api_key="sk-or-test-value")

    assert "sk-or-test-value" not in repr(settings)
    assert settings.openrouter_api_key is not None
    assert settings.openrouter_api_key.get_secret_value() == "sk-or-test-value"
