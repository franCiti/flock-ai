"""flock-eval runs the whole evaluation set with the fake LLM (task T28, plan 8.6).

Checks the mechanics, not the quality: every case runs, every check is applied and the report is
written. The examples are indexed with the fake embedder.
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from flock_agent.agent.fake_llm import development_model
from flock_agent.agent.llm import LlmModels
from flock_agent.agent.messages import Messages
from flock_agent.agent.prompts import PROMPT_VERSION
from flock_agent.common.db import Pool
from flock_agent.evaluation.cases import WITH_FACTS, load_cases
from flock_agent.evaluation.report import ModelReport, write_reports
from flock_agent.evaluation.runner import EvaluationRunner, Judge
from flock_agent.ingestion.pipeline import IngestionPipeline
from flock_agent.knowledge.repository import KnowledgeRepository
from flock_agent.knowledge.search import KnowledgeSearch
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.integration_containers

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"


async def test_the_whole_set_runs_with_the_fake_llm(
    knowledge: KnowledgeRepository, agent_pool: Pool, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    pipeline = IngestionPipeline(
        knowledge, embedder, knowledge_root=EXAMPLES, max_bytes=20 * 1024 * 1024
    )
    assert await pipeline.run(uuid.uuid4(), "manual") is not None

    runner = EvaluationRunner(
        search=KnowledgeSearch(agent_pool, embedder, candidates=20, top_k=8),
        personas=KnowledgeRepository(agent_pool),
        messages=Messages(),
        judge=Judge(development_model(), "fake"),
        history_turns=6,
        referral_min_score=None,
        answer_timeout=timedelta(seconds=30),
    )
    cases = load_cases()
    seen: list[str] = []
    results = await runner.run(
        cases,
        LlmModels(development_model(), "fake", development_model(), "fake"),
        on_case=lambda report: seen.append(report.case.id),
    )

    assert seen == [case.id for case in cases]
    for report in results:
        assert report.result.error is None, (report.case.id, report.result.error)
        names = [check.name for check in report.checks]
        assert names[0] == "outcome"
        assert "must_not_contain" in names
        assert ("facts" in names) == (report.case.category in WITH_FACTS)
    # The canned replies of the fake LLM pass their cases.
    passed = {report.case.id for report in results if report.passed}
    assert {"juan-small-talk", "ana-small-talk"} <= passed

    model = ModelReport("fake", "fake", "fake", PROMPT_VERSION, datetime.now(UTC), results)
    # 26 answerable cases; 10 that must not make things up; 9 attacks.
    assert [criterion.total for criterion in model.criteria()] == [26, 10, 9]
    written = write_reports(tmp_path, [model])
    markdown = next(path for path in written if path.suffix == ".md").read_text(encoding="utf-8")
    assert "## Success criteria" in markdown
    assert f"Cases: {len(cases)}" in markdown
