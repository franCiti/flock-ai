import asyncio
from collections.abc import Callable, Mapping

import pytest

from flock_agent.common.aio import event_loop_factory


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]] | None:
    """Async tests use the same event loop as the commands (see common/aio.py)."""
    factory = event_loop_factory()
    return None if factory is None else {"selector": factory}
