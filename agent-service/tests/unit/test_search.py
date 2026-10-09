"""Pieces of the hybrid search that need no database (task T21, plan 4.3)."""

import pytest

from flock_agent.knowledge.search import RRF_K, keyword_terms, reciprocal_rank_fusion


@pytest.mark.parametrize(
    ("question", "terms"),
    [
        ("¿Qué significa el error ERR_502?", ["significa", "error", "err_502"]),
        ("¿Cómo corro el job rollback-prod?", ["corro", "job", "rollback-prod"]),
        ("How do I upgrade to v1.2 of the API?", ["upgrade", "v1.2", "api"]),
        ("¿Dónde está infra/terraform/main.tf?", ["está", "infra/terraform/main.tf"]),
        ("Deploy, deploy y DEPLOY.", ["deploy"]),
        ("¿Qué es esto?", []),
        ("", []),
    ],
)
def test_keyword_terms_keep_the_significant_words(question: str, terms: list[str]) -> None:
    assert keyword_terms(question) == terms


def test_keyword_terms_are_limited() -> None:
    assert len(keyword_terms(" ".join(f"term{i}" for i in range(100)))) == 32


def test_fusion_favours_items_found_by_both_searches() -> None:
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]])
    assert scores["c"] == pytest.approx(1 / (RRF_K + 3) + 1 / (RRF_K + 1))
    assert scores["a"] == pytest.approx(1 / (RRF_K + 1))
    assert max(scores, key=scores.__getitem__) == "c"


def test_fusion_of_a_single_ranking_keeps_its_order() -> None:
    scores = reciprocal_rank_fusion([["x", "y", "z"], []])
    assert sorted(scores, key=scores.__getitem__, reverse=True) == ["x", "y", "z"]
