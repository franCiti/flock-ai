"""Evaluation runner (`flock-eval`). Implemented in T28."""

from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.cli import exit_not_implemented


def main() -> None:
    bootstrap()
    exit_not_implemented("flock-eval", task="T28")
