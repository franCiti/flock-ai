"""Evaluation runner (`flock-eval`, plan 8.6, D38).

Runs the cases of eval/cases.yaml against the graph (no Kafka) with the configured model, or with
each model of --models, and writes a report to eval/reports/. It needs the knowledge base with
the example personas (flock-ingest run over examples/knowledge) and the agent's certificate.

    flock-eval                                 # LLM_MODEL / LLM_FAST_MODEL of the settings
    flock-eval --models model-a,model-b+fast-b # compare: each item is MAIN or MAIN+FAST
    flock-eval --persona juan-plataforma --case juan-rollback-how

Uses OpenRouter only at the end of each stage (D41); with LLM_PROVIDER=fake it checks the
mechanics with canned answers.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from flock_agent.agent.llm import create_models
from flock_agent.agent.messages import load_messages
from flock_agent.agent.prompts import PROMPT_VERSION
from flock_agent.common.aio import run_async
from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.db import open_pool
from flock_agent.common.settings import Settings
from flock_agent.evaluation.cases import DEFAULT_CASES_FILE, Case, CasesFileError, load_cases
from flock_agent.evaluation.checks import CaseReport
from flock_agent.evaluation.report import DEFAULT_REPORTS_DIR, ModelReport, write_reports
from flock_agent.evaluation.runner import EvaluationRunner, create_judge
from flock_agent.knowledge.embeddings import FastEmbedEmbedder
from flock_agent.knowledge.repository import KnowledgeRepository
from flock_agent.knowledge.search import KnowledgeSearch

EXIT_BAD_INPUT = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flock-eval", description="Evaluate the agent.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_FILE, help="cases file")
    parser.add_argument(
        "--models", help="comma-separated models to compare; each one MAIN or MAIN+FAST"
    )
    parser.add_argument("--persona", action="append", help="only the cases of this persona")
    parser.add_argument("--case", action="append", help="only this case id (repeatable)")
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS_DIR, help="report folder")
    return parser


def parse_models(value: str | None, settings: Settings) -> list[tuple[str, str]]:
    """[(main, fast)]: from --models, or the configured LLM_MODEL / LLM_FAST_MODEL."""
    if not value:
        main = "fake" if settings.llm_provider == "fake" else settings.llm_model
        fast = "fake" if settings.llm_provider == "fake" else settings.effective_fast_model
        if main is None or fast is None:
            msg = "missing LLM setting: LLM_MODEL (or use --models)"
            raise ValueError(msg)
        return [(main, fast)]
    pairs = []
    for item in value.split(","):
        main, _, fast = item.strip().partition("+")
        if not main:
            msg = f"invalid --models item: {item!r}"
            raise ValueError(msg)
        pairs.append((main, fast or settings.llm_fast_model or main))
    return pairs


def select_cases(
    cases: Sequence[Case], personas: Sequence[str] | None, ids: Sequence[str] | None
) -> list[Case]:
    selected = [
        case
        for case in cases
        if (not personas or case.persona in personas) and (not ids or case.id in ids)
    ]
    return selected


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = bootstrap()
    try:
        cases = select_cases(load_cases(args.cases), args.persona, args.case)
        models = parse_models(args.models, settings)
    except (CasesFileError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(EXIT_BAD_INPUT) from error
    if not cases:
        print("No cases match the filters.", file=sys.stderr)
        raise SystemExit(EXIT_BAD_INPUT)
    run_async(_run(settings, cases, models, args.reports))


def _print_case(report: CaseReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    failed = ", ".join(check.name for check in report.failed_checks())
    print(f"  {status} {report.case.id}" + (f"  ({failed})" if failed else ""), flush=True)


async def _run(
    settings: Settings, cases: list[Case], models: list[tuple[str, str]], reports_dir: Path
) -> None:
    embedder = await asyncio.to_thread(
        FastEmbedEmbedder,
        settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    pool = await open_pool(settings, max_size=2)
    try:
        judge = create_judge(settings)
        runner = EvaluationRunner(
            search=KnowledgeSearch(
                pool,
                embedder,
                candidates=settings.retrieval_candidates,
                top_k=settings.retrieval_top_k,
            ),
            personas=KnowledgeRepository(pool),
            messages=load_messages(settings.messages_file),
            judge=judge,
            history_turns=settings.history_turns,
            referral_min_score=settings.referral_min_score,
            answer_timeout=settings.answer_timeout,
        )
        started = datetime.now(UTC)
        reports = []
        for main, fast in models:
            print(f"Model {main} (fast: {fast}), {len(cases)} cases:", flush=True)
            llms = create_models(
                settings.model_copy(update={"llm_model": main, "llm_fast_model": fast})
            )
            results = await runner.run(cases, llms, on_case=_print_case)
            report = ModelReport(main, fast, judge.name, PROMPT_VERSION, started, results)
            reports.append(report)
            for criterion in report.criteria():
                mark = "met" if criterion.met else "NOT met"
                print(
                    f"  {criterion.name}: {criterion.passed}/{criterion.total}"
                    f" ({criterion.rate:.0%}, goal {criterion.goal:.0%}) - {mark}"
                )
            p50, p95 = report.first_token_percentiles()
            print(f"  First token p50/p95: {p50} / {p95} ms")
    finally:
        await pool.close()
    for path in write_reports(reports_dir, reports):
        print(f"Report: {path}")
