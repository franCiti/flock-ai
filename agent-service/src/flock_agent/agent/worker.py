"""Agent Worker entry point (`flock-agent`). Implemented in T25."""

from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.cli import exit_not_implemented


def main() -> None:
    bootstrap()
    exit_not_implemented("flock-agent", task="T25")
