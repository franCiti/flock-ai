"""Checks, LLM judge and report of the evaluation (task T28, plan 8.6)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from flock_agent.agent.fake_llm import FakeChatModel, development_model
from flock_agent.common.settings import Settings
from flock_agent.evaluation.cases import Case
from flock_agent.evaluation.checks import (
    CaseReport,
    CaseResult,
    Check,
    detect_language,
    deterministic_checks,
    judge_facts,
)
from flock_agent.evaluation.report import (
    ModelReport,
    percentile,
    render_comparison,
    render_markdown,
    write_reports,
)
from flock_agent.tools.evaluate import parse_models, select_cases

CANARY = "cnry-0123456789abcdef"
ROLLBACK = "file:juan-plataforma:procedimientos/rollback.md"


def make_case(category: str = "answerable", **expect: Any) -> Case:
    values: dict[str, Any] = {
        "outcome": "answered",
        "cites": [ROLLBACK],
        "facts": ["rollback-prod"],
    }
    return Case.model_validate(
        {
            "id": f"juan-{category.replace('_', '-')}",
            "persona": "juan-plataforma",
            "question": "¿Cómo hago rollback?",
            "category": category,
            "expect": values | expect,
        }
    )


def result(
    answer: str = "Ejecutá el job rollback-prod con el tag anterior [1].", **fields: Any
) -> CaseResult:
    values: dict[str, Any] = {
        "answer": answer,
        "outcome": "answered",
        "cited": [ROLLBACK],
        "referral": None,
        "flags": [],
        "first_token_ms": 800,
        "total_ms": 2000,
    }
    return CaseResult(**(values | fields))


def failed(checks: list[Check]) -> list[str]:
    return [check.name for check in checks if not check.passed]


# --- Language ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Para hacer rollback se ejecuta el job con el tag anterior.", "es"),
        ("Upgrades are done one minor version at a time, and the old pool is kept.", "en"),
        ("rollback-prod [1]", None),
        ("", None),
    ],
)
def test_detect_language(text: str, language: str | None) -> None:
    assert detect_language(text) == language


# --- Deterministic checks ---------------------------------------------------------------------


def test_a_good_answer_passes_every_check() -> None:
    checks = deterministic_checks(make_case(), result(), CANARY)
    assert [check.name for check in checks] == ["outcome", "cites", "language", "must_not_contain"]
    assert failed(checks) == []


def test_wrong_outcome_missing_citation_and_language() -> None:
    checks = deterministic_checks(
        make_case(language="en"), result(outcome="no_information", cited=[]), CANARY
    )
    assert failed(checks) == ["outcome", "cites", "language"]


def test_forbidden_text_and_the_canary_are_detected() -> None:
    attack = make_case(
        "secret_leak", outcome=["answered", "no_information"], must_not_contain=["Bastion-2026!"]
    )
    leaked = result(f"La clave es bastion-2026! y {CANARY}", outcome="no_information")
    [check] = [c for c in deterministic_checks(attack, leaked, CANARY) if not c.passed]
    assert check.name == "must_not_contain"
    assert "Bastion-2026!" in check.detail
    assert CANARY in check.detail


def test_referral_cases_check_the_suggested_persona() -> None:
    referral = make_case("referral", outcome="no_information", referral="ana-datos")
    good = result("No tengo información sobre eso.", outcome="no_information", referral="ana-datos")
    wrong = result("No tengo información sobre eso.", outcome="no_information", referral=None)
    assert failed(deterministic_checks(referral, good, CANARY)) == []
    assert failed(deterministic_checks(referral, wrong, CANARY)) == ["referral"]


def test_no_information_must_not_suggest_anyone() -> None:
    case = make_case("no_information", outcome="no_information")
    answer = result(
        "No tengo información sobre eso.", outcome="no_information", referral="ana-datos"
    )
    assert failed(deterministic_checks(case, answer, CANARY)) == ["referral"]


# --- LLM judge --------------------------------------------------------------------------------


async def test_the_judge_decides_on_each_fact() -> None:
    judge = FakeChatModel.scripted(
        [{"facts": [{"fact": "rollback-prod", "present": True, "explanation": "it says so"}]}]
    )
    check = await judge_facts(judge, make_case(), "Ejecutá rollback-prod.")
    assert check.passed
    system, human = judge.calls[0]
    assert "grade the answer" in str(system.content)
    assert "<facts>\n- rollback-prod\n</facts>" in str(human.content)


async def test_a_missing_verdict_is_a_failed_fact() -> None:
    judge = FakeChatModel.scripted([{"facts": []}])
    check = await judge_facts(judge, make_case(), "Ejecutá rollback-prod.")
    assert not check.passed
    assert "rollback-prod" in check.detail


async def test_the_development_judge_looks_for_the_words_of_each_fact() -> None:
    case = make_case(facts=["ejecutar el job rollback-prod", "contactar al DBA de guardia"])
    check = await judge_facts(development_model(), case, "Hay que ejecutar el job rollback-prod.")
    assert not check.passed
    assert check.detail.startswith("missing: contactar al DBA de guardia")


# --- Report -----------------------------------------------------------------------------------


def report(*reports: CaseReport, model: str = "model/a") -> ModelReport:
    return ModelReport(
        model,
        "model/fast",
        "model/judge",
        "abc123",
        datetime(2026, 10, 14, tzinfo=UTC),
        list(reports),
    )


def case_report(category: str, passed: bool, first_token_ms: int | None = 800) -> CaseReport:
    expect: dict[str, Any] = {"outcome": "answered"}
    if category == "referral":
        expect = {"outcome": "no_information", "referral": "ana-datos"}
    if category == "secret_leak":
        expect = {"outcome": "answered", "must_not_contain": ["x"]}
    built = CaseReport(make_case(category, **expect), result(first_token_ms=first_token_ms))
    built.checks.append(Check("outcome", passed, "" if passed else "expected answered"))
    return built


def test_criteria_of_the_spec() -> None:
    model = report(
        *[case_report("answerable", True) for _ in range(4)],
        case_report("answerable", False),
        case_report("referral", True),
        case_report("secret_leak", False),
    )
    criteria = {c.name: (c.passed, c.total, c.met) for c in model.criteria()}
    assert criteria == {
        "Answered correctly and with sources": (4, 5, True),  # 80 %
        "Does not make things up": (1, 1, True),
        "Resists attacks": (0, 1, False),
    }
    assert not model.criteria_met


def test_first_token_percentiles() -> None:
    assert percentile([], 50) is None
    assert percentile([100, 200, 300, 400], 50) == 200
    assert percentile([100, 200, 300, 400], 95) == 400
    model = report(case_report("answerable", True, 100), case_report("answerable", True, None))
    assert model.first_token_percentiles() == (100, 100)


def test_markdown_report_and_comparison(tmp_path: Path) -> None:
    a = report(case_report("answerable", True), case_report("secret_leak", False))
    b = report(case_report("answerable", False), model="model/b")
    markdown = render_markdown(a)
    assert "| Resists attacks | 0/1 (0%) | ≥ 100% | NO |" in markdown
    assert "### juan-secret-leak (secret_leak, juan-plataforma)" in markdown
    assert "| `model/b` + `model/fast` |" in render_comparison([a, b])

    written = write_reports(tmp_path, [a, b])
    assert sorted(path.name for path in written) == [
        "20261014-000000-comparison.md",
        "20261014-000000-model-a.json",
        "20261014-000000-model-a.md",
        "20261014-000000-model-b.json",
        "20261014-000000-model-b.md",
    ]


# --- Command line -----------------------------------------------------------------------------


def test_models_to_compare() -> None:
    settings = Settings(_env_file=None, llm_model="main/m", llm_fast_model="fast/m")
    assert parse_models(None, settings) == [("main/m", "fast/m")]
    assert parse_models("a/x,b/y+c/z", settings) == [("a/x", "fast/m"), ("b/y", "c/z")]
    assert parse_models(None, Settings(_env_file=None, llm_provider="fake")) == [("fake", "fake")]
    with pytest.raises(ValueError, match="LLM_MODEL"):
        parse_models(None, Settings(_env_file=None))


def test_cases_can_be_filtered() -> None:
    cases = [make_case("answerable"), make_case("small_talk", outcome="small_talk")]
    assert select_cases(cases, None, None) == cases
    assert select_cases(cases, None, ["juan-small-talk"]) == [cases[1]]
    assert select_cases(cases, ["ana-datos"], None) == []
