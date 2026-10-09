"""Requests per minute per client app (spec HU15.5, plan section 3.3).

Fixed one-minute windows counted in the database, so the limit holds with several workers.
Every request counts, including the rejected ones.
"""

from datetime import UTC, datetime

from flock_agent.common.db import Pool


def window_start(at: datetime) -> datetime:
    """Start of the one-minute window that contains `at` (in UTC)."""
    return at.astimezone(UTC).replace(second=0, microsecond=0)


class RateLimiter:
    def __init__(self, pool: Pool, max_per_minute: int) -> None:
        self._pool = pool
        self._max_per_minute = max_per_minute

    async def acquire(self, client_id: str, *, at: datetime) -> bool:
        """Count a request received `at`; False if it exceeds the limit of its window."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO rate_limit_window (client_id, window_start, request_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (client_id, window_start) DO UPDATE SET
                    request_count = rate_limit_window.request_count + 1
                RETURNING request_count
                """,
                (client_id, window_start(at)),
            )
            row = await cursor.fetchone()
            if row is None:
                msg = "the rate limit upsert returned no row"
                raise RuntimeError(msg)
            return int(row[0]) <= self._max_per_minute

    async def purge(self, *, at: datetime) -> int:
        """Delete the windows that ended by `at` (all but its own); returns how many."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM rate_limit_window WHERE window_start < %s", (window_start(at),)
            )
            return cursor.rowcount
