"""Audit log of what was answered (spec HU8, HU15.7, plan section 3.3).

The table holds the same content as the AuditEntry message published to agent.audit, so both
are built from the contract model.
"""

from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from flock_agent.common.db import Pool
from flock_agent.contracts.generated.audit_entry_v1 import AuditEntry


class AuditLog:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def record(self, entry: AuditEntry) -> None:
        """Store an entry. Recording the same entry again changes nothing (redelivery)."""
        values = entry.model_dump(exclude={"version"})
        values["citations"] = Jsonb(
            [citation.model_dump(mode="json", by_alias=True) for citation in entry.citations]
        )
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO audit_entry (id, request_id, client_id, conversation_id, persona_id,
                                         question, answer, outcome, error_code, citations,
                                         referral_persona_id, flags, llm_model, prompt_version,
                                         first_token_ms, total_ms, created_at)
                VALUES (%(audit_id)s, %(request_id)s, %(client_id)s, %(conversation_id)s,
                        %(persona_id)s, %(question)s, %(answer)s, %(outcome)s, %(error_code)s,
                        %(citations)s, %(referral_persona_id)s, %(flags)s, %(llm_model)s,
                        %(prompt_version)s, %(first_token_ms)s, %(total_ms)s, %(created_at)s)
                ON CONFLICT (id) DO NOTHING
                """,
                values,
            )

    async def get(self, audit_id: UUID) -> AuditEntry | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(
                """
                SELECT id AS audit_id, request_id, client_id, conversation_id, persona_id,
                       question, answer, outcome, error_code, citations, referral_persona_id,
                       flags, llm_model, prompt_version, first_token_ms, total_ms, created_at
                FROM audit_entry WHERE id = %s
                """,
                (audit_id,),
            )
            row = await cursor.fetchone()
        return None if row is None else AuditEntry.model_validate({**row, "version": 1})
