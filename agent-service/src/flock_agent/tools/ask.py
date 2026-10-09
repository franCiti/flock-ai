"""Command-line test client (`flock-ask`). Implemented in T26."""

from flock_agent.common.bootstrap import bootstrap
from flock_agent.common.cli import exit_not_implemented


def main() -> None:
    bootstrap()
    exit_not_implemented("flock-ask", task="T26")
