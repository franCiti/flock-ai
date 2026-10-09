"""Ingestion entry point (`flock-ingest`).

`run` is implemented in T18 and `worker` in T34.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.cli import exit_not_implemented

_TASK_BY_COMMAND = {"run": "T18", "worker": "T34"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flock-ingest", description="Knowledge ingestion.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run a manual ingestion (development)")
    run.add_argument("--persona", help="only ingest this persona id")
    run.add_argument(
        "--sources",
        type=Path,
        help="JSON file with external sources, same format as IngestionJob.sources",
    )

    commands.add_parser("worker", help="start the Ingestion Worker (consumes ingestion.jobs)")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    bootstrap()
    exit_not_implemented(f"flock-ingest {args.command}", task=_TASK_BY_COMMAND[args.command])
