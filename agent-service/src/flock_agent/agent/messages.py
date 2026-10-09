"""Configurable bot messages, in Spanish (spec HU11, plan 1.3 and 4.3).

The operator edits config/messages.yaml; any message left out keeps its default. Messages may
use profile data as placeholders (`{display_name}`, and `{referral_name}` in the referral). The
`canned_reply` node adapts them to the language of the question (T22).
"""

import string
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CannedKey = Literal["about_assistant", "small_talk", "out_of_scope", "no_information", "referral"]
ErrorCode = Literal[
    "INVALID_REQUEST",
    "UNSUPPORTED_VERSION",
    "PERSONA_NOT_FOUND",
    "QUESTION_TOO_LONG",
    "RATE_LIMITED",
    "TIMEOUT",
    "LLM_UNAVAILABLE",
    "INTERNAL_ERROR",
]

DEFAULT_ERRORS: dict[ErrorCode, str] = {
    "INVALID_REQUEST": "El pedido no tiene un formato válido.",
    "UNSUPPORTED_VERSION": "La versión del pedido no está soportada.",
    "PERSONA_NOT_FOUND": "No se encontró la persona consultada.",
    "QUESTION_TOO_LONG": "La pregunta es demasiado larga. Probá con una más corta.",
    "RATE_LIMITED": (
        "Se recibieron demasiadas consultas en poco tiempo. Probá de nuevo en un minuto."
    ),
    "TIMEOUT": "La respuesta tardó demasiado. Probá de nuevo en unos minutos.",
    "LLM_UNAVAILABLE": (
        "El servicio no está disponible en este momento. Probá de nuevo en unos minutos."
    ),
    "INTERNAL_ERROR": "Ocurrió un error al procesar la consulta. Probá de nuevo en unos minutos.",
}

# Placeholders each message may use. Error messages and the secret placeholder take none.
_PROFILE = frozenset({"display_name"})
_PLACEHOLDERS: dict[str, frozenset[str]] = {
    "about_assistant": _PROFILE,
    "small_talk": _PROFILE,
    "out_of_scope": _PROFILE,
    "no_information": _PROFILE,
    "referral": _PROFILE | {"referral_name"},
}


class MessagesError(ValueError):
    """The messages file cannot be used."""


def _placeholders(template: str) -> set[str]:
    """Names between braces in `template` (`{{` and `}}` are literal braces)."""
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


class Messages(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    about_assistant: str = (
        "Soy el asistente virtual de {display_name}: respondo consultas con la información "
        "de su base de conocimiento, pero no soy {display_name}. ¿En qué te puedo ayudar?"
    )
    small_talk: str = (
        "¡Con gusto! Soy el asistente virtual de {display_name}. Si tenés una consulta, "
        "escribila y la busco en su base de conocimiento."
    )
    out_of_scope: str = (
        "Solo respondo con la información de la base de conocimiento de {display_name}, "
        "así que no puedo ayudarte con ese pedido."
    )
    no_information: str = (
        "No tengo información sobre eso en la base de conocimiento de {display_name}."
    )
    referral: str = "Quizás {referral_name} pueda ayudarte con esa consulta."
    # Replaces each secret found while indexing (plan 5.6, used by T12).
    secret_placeholder: str = "[dato oculto]"  # noqa: S105 (replaces secrets, is not one)
    errors: dict[ErrorCode, str] = Field(default_factory=lambda: dict(DEFAULT_ERRORS))

    @field_validator("errors")
    @classmethod
    def _complete_errors(cls, value: dict[ErrorCode, str]) -> dict[ErrorCode, str]:
        """Error codes left out keep their default message."""
        return {**DEFAULT_ERRORS, **value}

    @model_validator(mode="after")
    def _check_placeholders(self) -> "Messages":
        templates: dict[str, str] = {
            "secret_placeholder": self.secret_placeholder,
            **{key: getattr(self, key) for key in _PLACEHOLDERS},
            **{f"errors.{code}": text for code, text in self.errors.items()},
        }
        for key, template in templates.items():
            try:
                names = _placeholders(template)
            except ValueError as error:
                msg = f"{key}: invalid braces ({error}); write {{{{ or }}}} for a literal brace"
                raise ValueError(msg) from error
            allowed = _PLACEHOLDERS.get(key, frozenset())
            if unknown := names - allowed:
                accepted = ", ".join(f"{{{name}}}" for name in sorted(allowed)) or "none"
                msg = f"{key}: unknown placeholder {sorted(unknown)} (accepted: {accepted})"
                raise ValueError(msg)
            if not template.strip():
                msg = f"{key}: the message is empty"
                raise ValueError(msg)
        return self

    def canned(self, key: CannedKey, *, display_name: str, referral_name: str | None = None) -> str:
        """A canned reply filled in with the persona's profile data."""
        values = {"display_name": display_name}
        if key == "referral":
            if referral_name is None:
                msg = "the referral message needs referral_name"
                raise ValueError(msg)
            values["referral_name"] = referral_name
        template: str = getattr(self, key)
        return template.format(**values)

    def error(self, code: ErrorCode) -> str:
        return self.errors[code].format()


def load_messages(path: Path) -> Messages:
    """Read the messages file; raises MessagesError if it is missing or invalid."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        msg = f"cannot read the messages file {path}: {error}"
        raise MessagesError(msg) from error
    except yaml.YAMLError as error:
        msg = f"the messages file {path} is not valid YAML: {error}"
        raise MessagesError(msg) from error
    if data is None:
        data = {}
    if not isinstance(data, dict):
        msg = f"the messages file {path} must be a mapping of message names to texts"
        raise MessagesError(msg)
    try:
        return Messages.model_validate(data)
    except ValidationError as error:
        msg = f"invalid messages file {path}:\n{error}"
        raise MessagesError(msg) from error


# The codes of the contract (ErrorReply.code); a test keeps both lists equal.
ERROR_CODES: tuple[ErrorCode, ...] = get_args(ErrorCode)
