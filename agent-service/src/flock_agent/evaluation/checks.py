"""The checks of each evaluation case (plan 8.6, table "Cómo se mide cada caso")."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from flock_agent.agent.llm import structured
from flock_agent.agent.prompts import JUDGE
from flock_agent.evaluation.cases import WITH_FACTS, Case

# Frequent words of each language: enough to tell Spanish from English in an answer.
_SPANISH_WORDS = """
    el la los las de del que y en un una es se no por con para su al lo como más pero sus le ya o
    este si porque esta entre cuando muy sin sobre también hay hasta
"""
_ENGLISH_WORDS = """
    the of and to in is that it for on with as are be this was by not or at from have an they
    which you your can will if there their when one all should
"""
_LANGUAGE_WORDS = {
    "es": frozenset(_SPANISH_WORDS.split()),
    "en": frozenset(_ENGLISH_WORDS.split()),
}
_WORDS = re.compile(r"[^\W\d_]+")


def detect_language(text: str) -> str | None:
    """'es' or 'en' by their frequent words; None if the text gives no clue."""
    words = [word.lower() for word in _WORDS.findall(text)]
    scores = {
        language: sum(word in common for word in words)
        for language, common in _LANGUAGE_WORDS.items()
    }
    best = max(scores, key=lambda language: scores[language])
    others = [score for language, score in scores.items() if language != best]
    if scores[best] == 0 or scores[best] == max(others):
        return None
    return best


@dataclass(frozen=True)
class CaseResult:
    """What the agent answered for a case (the final state of the graph)."""

    answer: str
    outcome: str | None
    cited: list[str]  # document ids of the citations
    referral: str | None
    flags: list[str]
    first_token_ms: int | None
    total_ms: int
    error: str | None = None  # the run failed (exception); every check fails


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseReport:
    case: Case
    result: CaseResult
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.result.error is None and all(check.passed for check in self.checks)

    def failed_checks(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]


class FactVerdict(BaseModel):
    fact: str
    present: bool
    explanation: str = ""


class JudgeVerdict(BaseModel):
    """Structured output of the judge: one verdict per expected fact."""

    facts: list[FactVerdict] = Field(default_factory=list)


def deterministic_checks(case: Case, result: CaseResult, canary: str) -> list[Check]:
    """Every check that needs no LLM."""
    expect = case.expect
    checks = [
        Check(
            "outcome",
            result.outcome in expect.outcomes,
            f"expected {' or '.join(expect.outcomes)}, got {result.outcome}",
        )
    ]
    if case.category in WITH_FACTS:
        missing = [document for document in expect.cites if document not in result.cited]
        checks.append(Check("cites", not missing, f"not cited: {', '.join(missing)}"))
    if case.category == "referral" or expect.referral is not None:
        checks.append(
            Check(
                "referral",
                result.referral == expect.referral,
                f"expected {expect.referral}, got {result.referral}",
            )
        )
    elif case.category == "no_information":
        checks.append(
            Check("referral", result.referral is None, f"unexpected referral to {result.referral}")
        )
    language = detect_language(result.answer)
    checks.append(
        Check(
            "language",
            language == expect.language,
            f"expected {expect.language}, detected {language}",
        )
    )
    answer = result.answer.lower()
    forbidden = [text for text in [*expect.must_not_contain, canary] if text.lower() in answer]
    checks.append(Check("must_not_contain", not forbidden, f"contains: {', '.join(forbidden)}"))
    return checks


async def judge_facts(judge: BaseChatModel, case: Case, answer: str) -> Check:
    """LLM as a judge: are the expected facts in the answer? (answerable and partial cases)."""
    prompt = JUDGE.messages(
        question=case.question,
        answer=answer,
        facts="\n".join(f"- {fact}" for fact in case.expect.facts),
    )
    verdict = await structured(judge, JudgeVerdict).ainvoke(prompt)
    missing = _missing_facts(case.expect.facts, verdict.facts)
    explanations = "; ".join(f"{item.fact}: {item.explanation}" for item in verdict.facts)
    return Check("facts", not missing, f"missing: {', '.join(missing)} ({explanations})")


def _missing_facts(expected: Sequence[str], verdicts: Sequence[FactVerdict]) -> list[str]:
    """Facts without a positive verdict (matched by position; a missing verdict is a fail)."""
    return [
        fact
        for index, fact in enumerate(expected)
        if index >= len(verdicts) or not verdicts[index].present
    ]
