"""Helpers shared by the command-line entry points."""

import logging
from typing import NoReturn

EXIT_NOT_IMPLEMENTED = 2


def exit_not_implemented(command: str, task: str) -> NoReturn:
    """Stop a command whose behaviour belongs to a later backlog task."""
    logging.getLogger(__name__).error(
        "command not implemented yet", extra={"command": command, "task": task}
    )
    raise SystemExit(EXIT_NOT_IMPLEMENTED)
