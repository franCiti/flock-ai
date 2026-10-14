"""Calibrates REFERRAL_MIN_SCORE with the evaluation cases (plan 4.8 and 8.6, task T29).

For every case that should or should not suggest another persona, it searches the question in the
other personas (as find_referral does) and prints the best cosine similarity. A good threshold
lets every "should refer" case through and stops every "should not" one; the script proposes the
midpoint between both groups. No LLM is used: only the embeddings and the knowledge base.

Run from agent-service/ with the agent's certificate, after ingesting examples/knowledge:
    uv run python scripts/calibrate_referral.py

Partial cases search their whole question here; the agent searches only the missing part, which
the LLM writes, so their similarity is a lower bound.
"""

import asyncio

from flock_agent.common.aio import run_async
from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.db import open_pool
from flock_agent.evaluation.cases import load_cases
from flock_agent.knowledge.embeddings import FastEmbedEmbedder
from flock_agent.knowledge.search import KnowledgeSearch

SHOULD_REFER = {"referral", "partial"}
SHOULD_NOT_REFER = {"no_information", "out_of_scope"}


async def main() -> None:
    settings = bootstrap()
    embedder = await asyncio.to_thread(
        FastEmbedEmbedder, settings.embedding_model, cache_dir=settings.embedding_cache_dir
    )
    pool = await open_pool(settings, max_size=2)
    search = KnowledgeSearch(
        pool, embedder, candidates=settings.retrieval_candidates, top_k=settings.retrieval_top_k
    )
    refer: list[float] = []
    not_refer: list[float] = []
    try:
        for case in load_cases():
            if case.category not in SHOULD_REFER | SHOULD_NOT_REFER:
                continue
            matches = await search.search_other_personas(case.persona, case.question)
            best = matches[0] if matches else None
            similarity = best.similarity if best else 0.0
            group = refer if case.category in SHOULD_REFER else not_refer
            group.append(similarity)
            expected = case.expect.referral or "-"
            found = best.persona_id if best else "-"
            row = f"{similarity:6.3f}  {case.category:15s} expected {expected:16s} best {found:16s}"
            print(f"{row} {case.id}")
    finally:
        await pool.close()
    print()
    print(f"should refer:     min {min(refer):.3f}  max {max(refer):.3f}")
    print(f"should not refer: min {min(not_refer):.3f}  max {max(not_refer):.3f}")
    if min(refer) > max(not_refer):
        print(f"proposed REFERRAL_MIN_SCORE: {(min(refer) + max(not_refer)) / 2:.2f}")
    else:
        print("the groups overlap: no threshold separates them (the LLM confirmation decides)")


if __name__ == "__main__":
    run_async(main())
