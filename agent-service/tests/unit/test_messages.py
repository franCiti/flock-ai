"""Configurable bot messages (task T20, spec HU11)."""

from pathlib import Path
from typing import get_args

import pytest

from flock_agent.agent.messages import (
    DEFAULT_ERRORS,
    ERROR_CODES,
    Messages,
    MessagesError,
    load_messages,
)
from flock_agent.common.settings import Settings
from flock_agent.contracts.generated.agent_reply_v1 import ErrorReply


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "messages.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_file_has_the_default_messages() -> None:
    shipped = Settings(_env_file=None).messages_file
    assert load_messages(shipped) == Messages()


def test_there_is_a_message_for_every_error_code_of_the_contract() -> None:
    assert set(ERROR_CODES) == set(get_args(ErrorReply.model_fields["code"].annotation))
    assert set(DEFAULT_ERRORS) == set(ERROR_CODES)


def test_messages_are_filled_in_with_profile_data() -> None:
    messages = Messages()
    about = messages.canned("about_assistant", display_name="Juan Pérez")
    assert about.startswith("Soy el asistente virtual de Juan Pérez")
    assert "no soy Juan Pérez" in about
    referral = messages.canned("referral", display_name="Juan Pérez", referral_name="Ana Gómez")
    assert referral == "Quizás Ana Gómez pueda ayudarte con esa consulta."


def test_profile_data_with_braces_is_kept_as_is() -> None:
    reply = Messages().canned("no_information", display_name="Equipo {infra}")
    assert "Equipo {infra}" in reply


def test_the_referral_needs_the_name_of_the_other_persona() -> None:
    with pytest.raises(ValueError, match="referral_name"):
        Messages().canned("referral", display_name="Juan Pérez")


def test_messages_left_out_keep_their_default(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "small_talk: '¡Hola! Soy el bot de {display_name}.'\n"
        "errors:\n  TIMEOUT: Se agotó el tiempo.\n",
    )
    messages = load_messages(path)
    assert messages.canned("small_talk", display_name="Ana") == "¡Hola! Soy el bot de Ana."
    assert messages.error("TIMEOUT") == "Se agotó el tiempo."
    assert messages.error("INTERNAL_ERROR") == DEFAULT_ERRORS["INTERNAL_ERROR"]
    assert messages.no_information == Messages().no_information


def test_an_empty_file_uses_every_default(tmp_path: Path) -> None:
    assert load_messages(write(tmp_path, "# nothing yet\n")) == Messages()


def test_literal_braces_are_written_doubled(tmp_path: Path) -> None:
    messages = load_messages(write(tmp_path, "out_of_scope: 'Usá {{ y }} con {display_name}'\n"))
    assert messages.canned("out_of_scope", display_name="Ana") == "Usá { y } con Ana"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("no_information: 'No sé, {user}'\n", "unknown placeholder"),
        ("about_assistant: 'Soy {referral_name}'\n", "unknown placeholder"),
        ("small_talk: 'Hola {display_name.__class__}'\n", "unknown placeholder"),
        ("errors:\n  TIMEOUT: 'Tardó {display_name}'\n", "unknown placeholder"),
        ("referral: 'Preguntale a {referral_name'\n", "invalid braces"),
        ("no_information: '   '\n", "empty"),
        ("greeting: Hola\n", "Extra inputs"),
        ("errors:\n  NOT_A_CODE: Hola\n", "NOT_A_CODE"),
        ("- a list\n", "must be a mapping"),
        ("small_talk: [unclosed\n", "not valid YAML"),
    ],
)
def test_invalid_files_are_rejected_with_the_reason(tmp_path: Path, text: str, error: str) -> None:
    with pytest.raises(MessagesError, match=error):
        load_messages(write(tmp_path, text))


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(MessagesError, match="cannot read"):
        load_messages(tmp_path / "missing.yaml")
