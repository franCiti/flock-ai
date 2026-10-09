"""Prompt templates, their version and the canary (plan 4.5 and 4.6)."""

import hashlib
import secrets
import string
from collections.abc import Iterable
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


@dataclass(frozen=True)
class Prompt:
    """A system message plus a user message, with `{name}` placeholders.

    Values are inserted once and never parsed again, so braces in a question or a document
    are kept as they are.
    """

    name: str
    system: str
    human: str

    @property
    def variables(self) -> frozenset[str]:
        return frozenset(_placeholders(self.system) | _placeholders(self.human))

    def messages(self, **values: str) -> list[BaseMessage]:
        if missing := self.variables - values.keys():
            msg = f"prompt {self.name}: missing values {sorted(missing)}"
            raise ValueError(msg)
        if extra := values.keys() - self.variables:
            msg = f"prompt {self.name}: unexpected values {sorted(extra)}"
            raise ValueError(msg)
        return [
            SystemMessage(content=self.system.format(**values)),
            HumanMessage(content=self.human.format(**values)),
        ]


def prompt_version(prompts: Iterable[Prompt]) -> str:
    """Identifier of a set of prompts, recorded in the audit log with the model (plan 4.6).

    It is derived from their text, so it changes whenever any prompt changes and can never be
    forgotten.
    """
    digest = hashlib.sha256()
    for prompt in sorted(prompts, key=lambda prompt: prompt.name):
        for part in (prompt.name, prompt.system, prompt.human):
            digest.update(part.encode())
            digest.update(b"\0")
    return digest.hexdigest()[:12]


def new_canary() -> str:
    """A random secret for one request's system prompt (plan 4.5, spec HU13.3)."""
    return f"cnry-{secrets.token_hex(8)}"


def contains_canary(text: str, canary: str) -> bool:
    """Whether the prompt leaked into `text`: then the answer is discarded."""
    return canary.lower() in text.lower()
