"""Running asyncio code: a single place that picks the event loop."""

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any


def event_loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """psycopg's async mode does not support Windows' default ProactorEventLoop.

    Containers run Linux, where the default loop is fine; this matters for development on Windows.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop
    return None


def run_async[T](main: Coroutine[Any, Any, T]) -> T:
    """asyncio.run() with an event loop that every dependency supports."""
    return asyncio.run(main, loop_factory=event_loop_factory())
