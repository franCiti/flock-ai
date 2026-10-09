"""Requests already processed: a repeated request id is answered once (spec, edge cases).

Delivery is "at least once" (plan 4.1): the worker checks the request id before processing and
records it only after publishing the reply. If it dies halfway, the request is processed again.
"""

from datetime import datetime, timedelta
from uuid import UUID

from flock_agent.common.db import Pool

# How long a processed request id is remembered (plan section 3.3).
RETENTION = timedelta(days=7)


class ProcessedRequests:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def contains(self, request_id: UUID) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT 1 FROM processed_request WHERE request_id = %s", (request_id,)
            )
            return await cursor.fetchone() is not None

    async def add(self, request_id: UUID, client_id: str, *, at: datetime) -> bool:
        """Record a processed request; False if it was already recorded."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO processed_request (request_id, client_id, received_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (request_id) DO NOTHING
                """,
                (request_id, client_id, at),
            )
            return cursor.rowcount == 1

    async def purge(self, *, at: datetime) -> int:
        """Forget the requests older than RETENTION at `at`; returns how many."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM processed_request WHERE received_at < %s", (at - RETENTION,)
            )
            return cursor.rowcount
