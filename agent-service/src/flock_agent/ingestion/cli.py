"""Ingestion entry point (`flock-ingest`, plan 5.8).

`run` updates the knowledge base once, without Kafka (development and manual runs).
`worker` (consumes ingestion.jobs) is implemented in T34.
"""

import argparse
import asyncio
import logging
import uuid
from collections.abc import Sequence
from pathlib import Path

from flock_agent.agent.messages import load_messages
from flock_agent.common.aio import run_async
from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.cli import exit_not_implemented
from flock_agent.common.db import conninfo, open_pool
from flock_agent.common.migrations import apply_migrations
from flock_agent.common.settings import Settings
from flock_agent.ingestion.pipeline import IngestionPipeline, RunResult
from flock_agent.knowledge.embeddings import FastEmbedEmbedder
from flock_agent.knowledge.repository import KnowledgeRepository

log = logging.getLogger(__name__)

EXIT_FAILED = 1
EXIT_REJECTED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flock-ingest", description="Knowledge ingestion.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run a manual ingestion (development)")
    run.add_argument("--persona", help="only ingest this persona id")
    run.add_argument(
        "--sources",
        type=Path,
        help="JSON file with external sources, same format as IngestionJob.sources (stage 3)",
    )

    commands.add_parser("worker", help="start the Ingestion Worker (consumes ingestion.jobs)")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = bootstrap()
    if args.command == "worker":
        exit_not_implemented("flock-ingest worker", task="T34")
    if args.sources is not None:
        # TODO(T47+): external sources arrive in stage 3.
        exit_not_implemented("flock-ingest run --sources", task="T47")
    raise SystemExit(run_async(_run(settings, persona=args.persona)))


async def _run(settings: Settings, *, persona: str | None) -> int:
    applied = await asyncio.to_thread(apply_migrations, conninfo(settings), schema="knowledge")
    if applied:
        log.info("migrations applied", extra={"migrations": applied})

    messages = load_messages(settings.messages_file)
    embedder = await asyncio.to_thread(
        FastEmbedEmbedder,
        settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )
    pool = await open_pool(settings, max_size=2)
    try:
        pipeline = IngestionPipeline(
            KnowledgeRepository(pool),
            embedder,
            knowledge_root=settings.knowledge_root,
            max_bytes=settings.max_file_mb * 1024 * 1024,
            secret_placeholder=messages.secret_placeholder,
        )
        try:
            result = await pipeline.run(
                uuid.uuid4(), "manual", persona_ids={persona} if persona else None
            )
        except Exception as error:  # already logged with its traceback by the pipeline
            print(f"Knowledge update failed: {error}")
            return EXIT_FAILED
    finally:
        await pool.close()

    if result is None:
        print("Another knowledge update is already running.")
        return EXIT_REJECTED
    print(format_result(result))
    return 0


def format_result(result: RunResult) -> str:
    """Human-readable summary per persona (spec HU4.5)."""
    lines = []
    for persona in result.personas:
        lines.append(
            f"{persona.persona_id} ({persona.display_name}): {persona.added} added, "
            f"{persona.modified} modified, {persona.deleted} deleted, "
            f"{persona.unchanged} unchanged, {persona.secrets_masked} secrets masked"
        )
        lines.extend(f"  skipped {item.path}: {item.reason}" for item in persona.skipped)
        lines.extend(f"  source {key} failed: {reason}" for key, reason in persona.source_errors)
    lines.extend(f"removed persona {persona_id}" for persona_id in result.removed_personas)
    lines.extend(
        f"ignored folder {name} (not a valid persona id)" for name in result.ignored_folders
    )
    totals = result.totals()
    lines.append(
        f"Total: {totals.personas} personas, {totals.added} added, {totals.modified} modified, "
        f"{totals.deleted} deleted, {totals.unchanged} unchanged, {totals.skipped} skipped"
    )
    return "\n".join(lines)
