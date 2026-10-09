from pathlib import Path

import pytest

from flock_agent.common.cli import EXIT_NOT_IMPLEMENTED, exit_not_implemented
from flock_agent.ingestion.cli import build_parser


def test_ingest_run_accepts_persona_and_sources() -> None:
    args = build_parser().parse_args(["run", "--persona", "juan", "--sources", "sources.json"])

    assert args.command == "run"
    assert args.persona == "juan"
    assert args.sources == Path("sources.json")


def test_ingest_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_not_implemented_commands_exit_with_a_distinct_code() -> None:
    with pytest.raises(SystemExit) as exc_info:
        exit_not_implemented("flock-agent", task="T25")

    assert exc_info.value.code == EXIT_NOT_IMPLEMENTED
