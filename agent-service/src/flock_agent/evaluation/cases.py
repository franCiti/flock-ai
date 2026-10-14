"""Evaluation cases (`agent-service/eval/cases.yaml`, plan 8.6)."""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from flock_agent.agent.graph.state import Outcome

Category = Literal[
    "answerable",
    "partial",
    "referral",
    "no_information",
    "out_of_scope",
    "small_talk",
    "about_assistant",
    "injection_direct",
    "injection_indirect",
    "cross_persona",
    "secret_leak",
]
CATEGORIES: tuple[Category, ...] = (
    "answerable",
    "partial",
    "referral",
    "no_information",
    "out_of_scope",
    "small_talk",
    "about_assistant",
    "injection_direct",
    "injection_indirect",
    "cross_persona",
    "secret_leak",
)
ATTACKS: frozenset[Category] = frozenset(
    {"injection_direct", "injection_indirect", "cross_persona", "secret_leak"}
)
# Categories whose answer comes from the knowledge base: facts and citations are checked.
WITH_FACTS: frozenset[Category] = frozenset({"answerable", "partial"})

DEFAULT_CASES_FILE = Path(__file__).resolve().parents[3] / "eval" / "cases.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Expect(_Strict):
    # One outcome, or the acceptable ones (an attack may be answered in more than one way).
    outcome: Outcome | list[Outcome]
    cites: list[str] = Field(default_factory=list)  # document ids that must be cited
    facts: list[str] = Field(default_factory=list)  # checked by the LLM judge
    # Suggested persona id. For referral it must match; for no_information, None means "no
    # referral"; for the other categories it is only checked when set.
    referral: str | None = None
    must_not_contain: list[str] = Field(default_factory=list)  # case-insensitive
    language: Literal["es", "en"] = "es"

    @property
    def outcomes(self) -> list[Outcome]:
        return self.outcome if isinstance(self.outcome, list) else [self.outcome]


class Case(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    persona: str
    question: str = Field(min_length=1)
    # Questions asked before, in the same conversation (follow-up questions, spec HU5).
    previous: list[str] = Field(default_factory=list)
    category: Category
    expect: Expect

    @model_validator(mode="after")
    def _check_category(self) -> Self:
        expect = self.expect
        if self.category in WITH_FACTS and not (expect.facts and expect.cites):
            msg = f"{self.id}: {self.category} cases need facts and cites"
            raise ValueError(msg)
        if self.category == "referral" and expect.referral is None:
            msg = f"{self.id}: referral cases need the expected referral"
            raise ValueError(msg)
        if self.category in ATTACKS and not expect.must_not_contain:
            msg = f"{self.id}: attack cases need must_not_contain"
            raise ValueError(msg)
        return self


class CasesFileError(ValueError):
    """The cases file is missing or invalid."""


def load_cases(path: Path = DEFAULT_CASES_FILE) -> list[Case]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        msg = f"cannot read the cases file {path}: {error}"
        raise CasesFileError(msg) from error
    if not isinstance(data, list):
        msg = f"the cases file {path} must be a list of cases"
        raise CasesFileError(msg)
    try:
        cases = [Case.model_validate(item) for item in data]
    except ValidationError as error:
        msg = f"invalid case in {path}:\n{error}"
        raise CasesFileError(msg) from error
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            msg = f"repeated case id in {path}: {case.id}"
            raise CasesFileError(msg)
        seen.add(case.id)
    return cases
