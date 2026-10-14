"""Secret masking before indexing (plan section 5.6, spec HU15.4).

The content of every document goes through a list of regular-expression detectors before it is
split into fragments, so secrets never reach the knowledge base, the LLM or an answer. Each
match is replaced by a placeholder ("[dato oculto]", configurable in messages.yaml) and counted.

It is a defense against the *evident* secrets, not a perfect detector:
- Provider tokens and private keys have a recognizable shape and are always masked.
- In credentials inside URLs and in key/value pairs ("password: ...", "Password=...;") only the
  value is masked, and only if it looks like a secret (see `looks_like_secret`), so that prose
  such as "la contraseña: se pide al líder" is kept.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_PLACEHOLDER = "[dato oculto]"


@dataclass(frozen=True)
class RedactionResult:
    text: str
    masked: int  # how many secrets were replaced


# --- Detectors with a recognizable shape: the whole match is masked ---------------------------

_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
    r"(?:.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|[A-Za-z0-9+/=\s]*)",
    re.DOTALL,
)
_PROVIDER_TOKENS = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    "slack_token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    # OpenAI, OpenRouter and Anthropic keys: sk-..., sk-proj-..., sk-or-v1-..., sk-ant-...
    "api_secret_key": re.compile(r"\bsk-(?:[a-z0-9]+-){0,2}[A-Za-z0-9_-]{20,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
}

# --- Detectors of a value next to a name: only the value is masked ----------------------------

# scheme://user:password@host -> the password
_URL_CREDENTIALS = re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:(?P<value>[^/\s@]+)@", re.I)

_CREDENTIAL_FIELDS = (
    r"password|passwd|pwd|contrase(?:ñ|n)a|clave|secret(?:[ _-]?(?:access[ _-]?)?key)?"
    r"|client[ _-]?secret|api[ _-]?key|apikey|access[ _-]?token|auth[ _-]?token|token"
    r"|private[ _-]?key|account[ _-]?key|shared[ _-]?access[ _-]?key"
)
# "password: x", "AWS secret key: x", "Password=x;", "\"api_key\": \"x\"", "**clave** = x"
_KEY_VALUE = re.compile(
    rf"(?<![\w-])(?:[a-z0-9]+[ _-])?(?:{_CREDENTIAL_FIELDS})(?![\w-])[\"'*`]*\s*(?:=>|[:=])\s*"
    r"(?P<value>\"[^\"\n]+\"|'[^'\n]+'|[^\s;,'\"]+)",
    re.IGNORECASE,
)

_MIN_SECRET_CHARS = 6
_LONG_SECRET_CHARS = 16
# Values that name a secret instead of containing it.
_REFERENCE = re.compile(r"^(?:\$\{.*\}|\$[A-Z_]+|<.*>|\{\{.*\}\}|%.*%|[*xX•.]+|\[.*\])$")


def looks_like_secret(value: str) -> bool:
    """Whether a value next to a secret's name is the secret itself, not a word or a reference.

    It must have no spaces, at least 6 characters and a digit, a symbol or an inner capital
    letter (or be long: 16 characters or more). "Bastion-2026!" is a secret; "secreta",
    "Solicitarla", "${DB_PASSWORD}" and "********" are not.
    """
    if len(value) < _MIN_SECRET_CHARS or any(char.isspace() for char in value):
        return False
    if _REFERENCE.match(value):
        return False
    has_digit = any(char.isdigit() for char in value)
    has_symbol = any(not char.isalnum() for char in value)
    has_inner_capital = any(char.isupper() for char in value[1:])
    return has_digit or has_symbol or has_inner_capital or len(value) >= _LONG_SECRET_CHARS


def _mask_value(pattern: re.Pattern[str], placeholder: str) -> Callable[[str], tuple[str, int]]:
    def apply(text: str) -> tuple[str, int]:
        count = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal count
            raw = match.group("value")
            value = raw[1:-1] if raw[:1] in "\"'" and raw[-1:] == raw[:1] else raw
            if not looks_like_secret(value):
                return match.group(0)
            count += 1
            start, end = match.span("value")
            offset = match.start()
            quote = raw[0] if value != raw else ""
            whole = match.group(0)
            return whole[: start - offset] + f"{quote}{placeholder}{quote}" + whole[end - offset :]

        return pattern.sub(replace, text), count

    return apply


def _mask_whole(pattern: re.Pattern[str], placeholder: str) -> Callable[[str], tuple[str, int]]:
    def apply(text: str) -> tuple[str, int]:
        return pattern.subn(placeholder, text)

    return apply


def redact(text: str, placeholder: str = DEFAULT_PLACEHOLDER) -> RedactionResult:
    """`text` with its evident secrets replaced by `placeholder`, and how many there were."""
    detectors = [
        _mask_whole(_PRIVATE_KEY, placeholder),
        *(_mask_whole(pattern, placeholder) for pattern in _PROVIDER_TOKENS.values()),
        _mask_value(_URL_CREDENTIALS, placeholder),
        _mask_value(_KEY_VALUE, placeholder),
    ]
    masked = 0
    for detector in detectors:
        text, count = detector(text)
        masked += count
    return RedactionResult(text=text, masked=masked)
