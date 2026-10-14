"""Runs the evaluation cases directly against the graph, without Kafka (plan 8.6).

Each case gets its own conversation (thread); its `previous` questions are asked first. The
knowledge base must already hold the personas of the cases (flock-ingest run over
examples/knowledge).
"""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from flock_agent.agent.fake_llm import development_model
from flock_agent.agent.graph.answer import ANSWER_STREAM_TAG
from flock_agent.agent.graph.builder import Graph, build_graph, checkpoint_serializer
from flock_agent.agent.graph.deps import Dependencies, Searcher
from flock_agent.agent.graph.state import AgentState, PersonaRef, turn_input
from flock_agent.agent.llm import LlmModels, openrouter_chat_model
from flock_agent.agent.messages import Messages
from flock_agent.agent.prompts import new_canary
from flock_agent.common.settings import Settings
from flock_agent.evaluation.cases import WITH_FACTS, Case
from flock_agent.evaluation.checks import (
    CaseReport,
    CaseResult,
    Check,
    deterministic_checks,
    judge_facts,
)
from flock_agent.knowledge.models import Persona

log = logging.getLogger(__name__)


class PersonaDirectory(Protocol):
    async def get_persona(self, persona_id: str) -> Persona | None: ...


@dataclass(frozen=True)
class Judge:
    model: BaseChatModel
    name: str


def create_judge(settings: Settings) -> Judge:
    """The judge's own model (EVAL_JUDGE_MODEL), distinct from the evaluated one when possible."""
    if settings.llm_provider == "fake":
        return Judge(development_model(), "fake")
    name = settings.eval_judge_model or settings.effective_fast_model
    if name is None:
        msg = "missing LLM setting: EVAL_JUDGE_MODEL (or LLM_MODEL)"
        raise ValueError(msg)
    if settings.eval_judge_model is None:
        log.warning("EVAL_JUDGE_MODEL is not set: the judge is the evaluated fast model")
    return Judge(openrouter_chat_model(settings, name), name)


class EvaluationRunner:
    def __init__(
        self,
        *,
        search: Searcher,
        personas: PersonaDirectory,
        messages: Messages,
        judge: Judge,
        history_turns: int,
        referral_min_score: float | None,
        answer_timeout: timedelta,
    ) -> None:
        self._search = search
        self._personas = personas
        self._messages = messages
        self._judge = judge
        self._history_turns = history_turns
        self._referral_min_score = referral_min_score
        self._answer_timeout = answer_timeout

    async def run(
        self,
        cases: Sequence[Case],
        models: LlmModels,
        on_case: Callable[[CaseReport], None] | None = None,
    ) -> list[CaseReport]:
        deps = Dependencies(
            main_model=models.main,
            fast_model=models.fast,
            search=self._search,
            messages=self._messages,
            history_turns=self._history_turns,
            referral_min_score=self._referral_min_score,
        )
        graph = build_graph(deps, InMemorySaver(serde=checkpoint_serializer()))
        reports = []
        for case in cases:
            report = await self._run_case(graph, case)
            reports.append(report)
            if on_case is not None:
                on_case(report)
        return reports

    async def _run_case(self, graph: Graph, case: Case) -> CaseReport:
        persona = await self._personas.get_persona(case.persona)
        if persona is None:
            reason = f"persona {case.persona} not found: ingest examples/knowledge first"
            return CaseReport(case, CaseResult("", None, [], None, [], None, 0, error=reason))
        ref = PersonaRef(id=persona.id, display_name=persona.display_name)
        config: RunnableConfig = {"configurable": {"thread_id": f"eval:{case.id}"}}
        canary = new_canary()
        for question in case.previous:
            await self._ask(graph, question, ref, config, new_canary())
        result = await self._ask(graph, case.question, ref, config, canary)
        report = CaseReport(case, result)
        if result.error is not None:
            report.checks.append(Check("run", False, result.error))
            return report
        report.checks.extend(deterministic_checks(case, result, canary))
        if case.category in WITH_FACTS:
            try:
                report.checks.append(await judge_facts(self._judge.model, case, result.answer))
            except Exception as error:  # the judge failing must not stop the evaluation
                report.checks.append(Check("facts", False, f"judge failed: {error}"))
        return report

    async def _ask(
        self,
        graph: Graph,
        question: str,
        persona: PersonaRef,
        config: RunnableConfig,
        canary: str,
    ) -> CaseResult:
        started = time.monotonic()
        first_token: float | None = None
        state: AgentState | None = None
        try:
            async with asyncio.timeout(self._answer_timeout.total_seconds()):
                async for mode, payload in graph.astream(
                    turn_input(question, persona, canary),
                    config,
                    stream_mode=["messages", "values"],
                ):
                    if mode == "values":
                        state = cast(AgentState, payload)
                        continue
                    chunk, metadata = cast(tuple[BaseMessage, dict[str, Any]], payload)
                    tags = metadata.get("tags", [])
                    if first_token is None and ANSWER_STREAM_TAG in tags and chunk.text:
                        first_token = time.monotonic()
        except TimeoutError:
            return _failed("timeout", started)
        except Exception as error:
            log.exception("evaluation case failed")
            return _failed(f"{type(error).__name__}: {error}", started)
        if state is None:
            return _failed("the graph returned no state", started)
        referral = state.get("referral")
        return CaseResult(
            answer=state.get("answer", ""),
            outcome=state.get("outcome"),
            cited=[citation["document_id"] for citation in state.get("citations", [])],
            referral=None if referral is None else referral["persona_id"],
            flags=list(state.get("flags", [])),
            first_token_ms=None if first_token is None else _ms(started, first_token),
            total_ms=_ms(started, time.monotonic()),
        )


def _ms(start: float, end: float) -> int:
    return max(0, round((end - start) * 1000))


def _failed(error: str, started: float) -> CaseResult:
    return CaseResult("", None, [], None, [], None, _ms(started, time.monotonic()), error=error)
