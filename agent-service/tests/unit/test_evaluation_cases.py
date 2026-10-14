"""The evaluation set (task T28, plan 8.6, spec success criterion 1)."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from flock_agent.evaluation.cases import CATEGORIES, Case, CasesFileError, load_cases

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"
CASES = load_cases()
PERSONAS = sorted({case.persona for case in CASES})


def test_both_example_personas_have_at_least_20_cases() -> None:
    assert PERSONAS == ["ana-datos", "juan-plataforma"]
    counts = Counter(case.persona for case in CASES)
    assert all(count >= 20 for count in counts.values()), counts


@pytest.mark.parametrize("persona", PERSONAS)
def test_every_category_is_covered_for_each_persona(persona: str) -> None:
    categories = {case.category for case in CASES if case.persona == persona}
    assert categories == set(CATEGORIES)


def test_cited_documents_exist_in_the_examples() -> None:
    for case in CASES:
        for document_id in case.expect.cites:
            kind, persona, path = document_id.split(":", 2)
            assert kind == "file", case.id
            assert persona == case.persona, case.id
            assert (EXAMPLES / persona / path).is_file(), (case.id, path)


def test_referrals_point_to_another_example_persona() -> None:
    for case in CASES:
        if case.expect.referral is not None:
            assert case.expect.referral in PERSONAS, case.id
            assert case.expect.referral != case.persona, case.id


def case(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": "juan-x",
        "persona": "juan-plataforma",
        "question": "¿Cómo hago rollback?",
        "category": "answerable",
        "expect": {"outcome": "answered", "cites": ["file:x:y.md"], "facts": ["algo"]},
    }
    return values | changes


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"expect": {"outcome": "answered"}}, "need facts and cites"),
        ({"category": "referral", "expect": {"outcome": "no_information"}}, "expected referral"),
        ({"category": "secret_leak", "expect": {"outcome": "answered"}}, "must_not_contain"),
        ({"category": "invented"}, "category"),
        ({"expect": {"outcome": "maybe"}}, "outcome"),
        ({"id": "Mayúsculas"}, "id"),
    ],
)
def test_invalid_cases_are_rejected(changes: dict[str, Any], error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        Case.model_validate(case(**changes))


def test_an_attack_may_accept_several_outcomes() -> None:
    parsed = Case.model_validate(
        case(
            category="injection_direct",
            expect={"outcome": ["about_assistant", "out_of_scope"], "must_not_contain": ["x"]},
        )
    )
    assert parsed.expect.outcomes == ["about_assistant", "out_of_scope"]


def test_repeated_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(
        "- {id: a, persona: p, question: q, category: small_talk, expect: {outcome: small_talk}}\n"
        "- {id: a, persona: p, question: q, category: small_talk, expect: {outcome: small_talk}}\n",
        encoding="utf-8",
    )
    with pytest.raises(CasesFileError, match="repeated case id"):
        load_cases(path)
