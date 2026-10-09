"""Conversation retention by last message (spec HU5.3, plan section 3.3).

Each conversation maps to a LangGraph thread `<clientId>:<conversationId>:<generation>`. The
generation goes up when the conversation expires or is asked to another persona, so the new
question starts without history.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from flock_agent.common.db import Pool


def thread_id(client_id: str, conversation_id: str, generation: int) -> str:
    """LangGraph thread of one generation of a conversation."""
    return f"{client_id}:{conversation_id}:{generation}"


@dataclass(frozen=True)
class ConversationThread:
    client_id: str
    conversation_id: str
    generation: int

    @property
    def thread_id(self) -> str:
        return thread_id(self.client_id, self.conversation_id, self.generation)

    def all_thread_ids(self) -> list[str]:
        """Threads of this and every previous generation."""
        return [
            thread_id(self.client_id, self.conversation_id, generation)
            for generation in range(self.generation + 1)
        ]


DeleteThreads = Callable[[Sequence[str]], Awaitable[None]]


class ConversationStore:
    """Resolves the thread of each question and forgets expired conversations."""

    def __init__(self, pool: Pool, ttl: timedelta) -> None:
        self._pool = pool
        self._ttl = ttl

    async def resolve(
        self, client_id: str, conversation_id: str, persona_id: str, *, at: datetime
    ) -> ConversationThread:
        """Register a question received `at` and return the thread it belongs to.

        One atomic upsert: a new conversation starts at generation 0; an existing one moves to
        the next generation if more than the TTL passed since its last message or the persona
        changed. Either way, `at` becomes its last message.
        """
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO conversation (client_id, conversation_id, persona_id, last_message_at)
                VALUES (%(client_id)s, %(conversation_id)s, %(persona_id)s, %(at)s)
                ON CONFLICT (client_id, conversation_id) DO UPDATE SET
                    generation = conversation.generation + CASE
                        WHEN conversation.persona_id <> EXCLUDED.persona_id
                          OR EXCLUDED.last_message_at - conversation.last_message_at > %(ttl)s
                        THEN 1 ELSE 0 END,
                    persona_id = EXCLUDED.persona_id,
                    last_message_at = GREATEST(conversation.last_message_at,
                                               EXCLUDED.last_message_at)
                RETURNING generation
                """,
                {
                    "client_id": client_id,
                    "conversation_id": conversation_id,
                    "persona_id": persona_id,
                    "at": at,
                    "ttl": self._ttl,
                },
            )
            row = await cursor.fetchone()
            if row is None:
                msg = "the conversation upsert returned no row"
                raise RuntimeError(msg)
            return ConversationThread(client_id, conversation_id, int(row[0]))

    async def purge_expired(self, delete_threads: DeleteThreads, *, at: datetime) -> int:
        """Forget the conversations expired at `at`; returns how many.

        `delete_threads` removes their LangGraph checkpoints (every generation). It runs before
        the rows are deleted, and a row is only deleted if it is still expired: a question that
        arrives meanwhile moves the conversation to a new generation and keeps it. Deleting the
        row first could let a new question reuse generation 0 and then lose its checkpoints.
        """
        cutoff = at - self._ttl
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT client_id, conversation_id, generation FROM conversation
                WHERE last_message_at < %s
                """,
                (cutoff,),
            )
            expired = [
                ConversationThread(str(c), str(v), int(g)) for c, v, g in await cursor.fetchall()
            ]
        if not expired:
            return 0
        await delete_threads(
            [tid for conversation in expired for tid in conversation.all_thread_ids()]
        )
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM conversation AS c
                USING unnest(%s::text[], %s::text[]) AS e (client_id, conversation_id)
                WHERE c.client_id = e.client_id AND c.conversation_id = e.conversation_id
                  AND c.last_message_at < %s
                """,
                (
                    [conversation.client_id for conversation in expired],
                    [conversation.conversation_id for conversation in expired],
                    cutoff,
                ),
            )
            return cursor.rowcount
