"""Access to the `knowledge` schema (plan section 3.2)."""

from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from pgvector import Vector
from psycopg import sql
from psycopg.rows import class_row, dict_row
from psycopg.types.json import Jsonb

from flock_agent.common.db import Pool
from flock_agent.knowledge.models import (
    ChunkInput,
    DocumentRecord,
    IngestionRun,
    Persona,
    RunStatus,
    RunTrigger,
    SyncState,
)

# Session-level advisory lock that allows a single ingestion at a time (spec HU4.9).
# Any 64-bit number works, as long as every process uses the same one.
INGESTION_LOCK_KEY = 0x666C6F636B_0001  # "flock" + 1

# Keys of the meta table.
META_EMBEDDING_MODEL = "embedding_model"
META_DIMENSIONS = "embedding_dimensions"


class IngestionAlreadyRunningError(RuntimeError):
    """Another process holds the ingestion lock."""


class KnowledgeRepository:
    """Reads and writes the knowledge base. Writing requires the `ingestion` role."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    # --- Personas ---------------------------------------------------------------------------

    async def upsert_persona(self, persona: Persona) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO persona (id, display_name, identities, profile_hash)
                VALUES (%(id)s, %(display_name)s, %(identities)s, %(profile_hash)s)
                ON CONFLICT (id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    identities = EXCLUDED.identities,
                    profile_hash = EXCLUDED.profile_hash,
                    updated_at = now()
                """,
                {**persona.model_dump(), "identities": Jsonb(persona.identities)},
            )

    async def get_persona(self, persona_id: str) -> Persona | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=class_row(Persona))
            await cursor.execute(
                "SELECT id, display_name, identities, profile_hash FROM persona WHERE id = %s",
                (persona_id,),
            )
            return await cursor.fetchone()

    async def list_personas(self) -> list[Persona]:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=class_row(Persona))
            await cursor.execute(
                "SELECT id, display_name, identities, profile_hash FROM persona ORDER BY id"
            )
            return await cursor.fetchall()

    async def delete_persona(self, persona_id: str) -> None:
        """Delete a persona and, in cascade, all of its knowledge."""
        async with self._pool.connection() as connection:
            await connection.execute("DELETE FROM persona WHERE id = %s", (persona_id,))

    # --- Documents and chunks ---------------------------------------------------------------

    async def get_content_hash(self, document_id: str) -> str | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT content_hash FROM document WHERE id = %s", (document_id,)
            )
            row = await cursor.fetchone()
            return None if row is None else str(row[0])

    async def replace_document(
        self, document: DocumentRecord, chunks: Sequence[ChunkInput]
    ) -> None:
        """Store a document and its chunks, replacing any previous version.

        One transaction: readers see the whole previous version or the whole new one, never a
        mix (spec, edge cases).
        """
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                """
                INSERT INTO document (id, persona_id, source_type, source_id, parent_id, title,
                                      url, path, section_hint, source_updated_at, content_hash,
                                      secrets_masked)
                VALUES (%(id)s, %(persona_id)s, %(source_type)s, %(source_id)s, %(parent_id)s,
                        %(title)s, %(url)s, %(path)s, %(section_hint)s, %(source_updated_at)s,
                        %(content_hash)s, %(secrets_masked)s)
                ON CONFLICT (id) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    source_id = EXCLUDED.source_id,
                    parent_id = EXCLUDED.parent_id,
                    title = EXCLUDED.title,
                    url = EXCLUDED.url,
                    path = EXCLUDED.path,
                    section_hint = EXCLUDED.section_hint,
                    source_updated_at = EXCLUDED.source_updated_at,
                    content_hash = EXCLUDED.content_hash,
                    secrets_masked = EXCLUDED.secrets_masked,
                    indexed_at = now()
                """,
                document.model_dump(),
            )
            await connection.execute("DELETE FROM chunk WHERE document_id = %s", (document.id,))
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    """
                    INSERT INTO chunk (document_id, persona_id, ordinal, heading_path, content,
                                       embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            document.id,
                            document.persona_id,
                            chunk.ordinal,
                            chunk.heading_path,
                            chunk.content,
                            Vector(list(chunk.embedding)),
                        )
                        for chunk in chunks
                    ],
                )

    async def document_ids(self, persona_id: str, source_id: str | None) -> set[str]:
        """Ids of the documents of one source of a persona (None = its folder)."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT id FROM document
                WHERE persona_id = %s AND source_id IS NOT DISTINCT FROM %s
                """,
                (persona_id, source_id),
            )
            return {str(row[0]) for row in await cursor.fetchall()}

    async def child_ids(self, parent_id: str) -> set[str]:
        """Ids of the documents attached to `parent_id` (an email's attachments)."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT id FROM document WHERE parent_id = %s", (parent_id,)
            )
            return {str(row[0]) for row in await cursor.fetchall()}

    async def delete_documents(self, document_ids: Iterable[str]) -> int:
        """Delete documents (their chunks and attachments go in cascade); returns how many."""
        ids = list(document_ids)
        if not ids:
            return 0
        async with self._pool.connection() as connection:
            cursor = await connection.execute("DELETE FROM document WHERE id = ANY(%s)", (ids,))
            return cursor.rowcount

    async def delete_documents_of_other_sources(
        self, persona_id: str, keep_source_ids: Iterable[str]
    ) -> int:
        """Delete the external-source documents of a persona whose source is no longer
        configured (spec HU12.4). Documents of the persona folder are kept."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM document
                WHERE persona_id = %s AND source_id IS NOT NULL AND NOT (source_id = ANY(%s))
                """,
                (persona_id, list(keep_source_ids)),
            )
            return cursor.rowcount

    # --- Sync state -------------------------------------------------------------------------

    async def get_sync_state(self, persona_id: str, source_key: str) -> SyncState | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=class_row(SyncState))
            await cursor.execute(
                """
                SELECT cursor, last_synced_at FROM sync_state
                WHERE persona_id = %s AND source_key = %s
                """,
                (persona_id, source_key),
            )
            return await cursor.fetchone()

    async def save_sync_state(
        self, persona_id: str, source_key: str, cursor: dict[str, Any]
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO sync_state (persona_id, source_key, cursor) VALUES (%s, %s, %s)
                ON CONFLICT (persona_id, source_key) DO UPDATE SET
                    cursor = EXCLUDED.cursor, last_synced_at = now()
                """,
                (persona_id, source_key, Jsonb(cursor)),
            )

    # --- Ingestion runs and lock ------------------------------------------------------------

    async def start_run(self, job_id: UUID, trigger: RunTrigger) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "INSERT INTO ingestion_run (job_id, trigger, status) VALUES (%s, %s, 'running')",
                (job_id, trigger),
            )

    async def finish_run(
        self, job_id: UUID, status: RunStatus, summary: dict[str, Any] | None
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE ingestion_run SET status = %s, summary = %s, finished_at = now()
                WHERE job_id = %s
                """,
                (status, None if summary is None else Jsonb(summary), job_id),
            )

    async def get_run(self, job_id: UUID) -> IngestionRun | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=class_row(IngestionRun))
            await cursor.execute(
                """
                SELECT job_id, trigger, status, started_at, finished_at, summary
                FROM ingestion_run WHERE job_id = %s
                """,
                (job_id,),
            )
            return await cursor.fetchone()

    @asynccontextmanager
    async def ingestion_lock(self) -> AsyncIterator[None]:
        """Hold the ingestion lock for the duration of the block (spec HU4.9).

        The lock belongs to the database session: if the process dies, it is released too.
        Raises IngestionAlreadyRunningError if another process holds it.
        """
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT pg_try_advisory_lock(%s)", (INGESTION_LOCK_KEY,)
            )
            row = await cursor.fetchone()
            if row is None or row[0] is not True:
                raise IngestionAlreadyRunningError
            try:
                yield
            finally:
                await connection.execute("SELECT pg_advisory_unlock(%s)", (INGESTION_LOCK_KEY,))

    # --- Embedding model ----------------------------------------------------------------------

    async def reset_for_embedding_model(self, model_name: str, dimensions: int) -> None:
        """Prepare the knowledge base for another embedding model, in one transaction.

        Vectors of different models are not comparable: every document is deleted (chunks go in
        cascade) and every sync cursor too, so the next update re-indexes everything. Personas
        are kept. The vector column is rebuilt with the new dimensions (its index follows).
        Must run while holding the ingestion lock.
        """
        alter = sql.SQL("ALTER TABLE chunk ALTER COLUMN embedding TYPE public.vector({})").format(
            sql.Literal(dimensions)
        )
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute("DELETE FROM document")
            await connection.execute("DELETE FROM sync_state")
            await connection.execute(alter)
            for key, value in ((META_EMBEDDING_MODEL, model_name), (META_DIMENSIONS, dimensions)):
                await connection.execute(
                    """
                    INSERT INTO meta (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (key, str(value)),
                )

    # --- Meta -------------------------------------------------------------------------------

    async def get_meta(self, key: str) -> str | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute("SELECT value FROM meta WHERE key = %s", (key,))
            row = await cursor.fetchone()
            return None if row is None else str(row["value"])

    async def set_meta(self, key: str, value: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO meta (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value),
            )
