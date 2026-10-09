import asyncio
import sys

from flock_agent.common.aio import run_async


async def current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_run_async_returns_the_result() -> None:
    async def answer() -> int:
        return 42

    assert run_async(answer()) == 42


def test_run_async_uses_a_loop_psycopg_supports() -> None:
    loop = run_async(current_loop())

    if sys.platform == "win32":
        assert isinstance(loop, asyncio.SelectorEventLoop)
