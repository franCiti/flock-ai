"""Records of the knowledge base (plan section 3.2)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["file", "email", "email_attachment", "jira", "confluence", "sharepoint"]
RunTrigger = Literal["scheduled", "manual"]
RunStatus = Literal["running", "completed", "failed", "rejected"]

PERSONA_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Persona(_Record):
    id: str = Field(pattern=PERSONA_ID_PATTERN)
    display_name: str = Field(min_length=1)
    identities: dict[str, str] = Field(default_factory=dict)
    profile_hash: str


class DocumentRecord(_Record):
    """Metadata of an indexed document. Its text lives in its chunks."""

    id: str
    persona_id: str
    source_type: SourceType
    source_id: str | None = None
    parent_id: str | None = None
    title: str
    url: str | None = None
    path: str | None = None
    section_hint: str | None = None
    source_updated_at: datetime
    content_hash: str
    secrets_masked: int = Field(default=0, ge=0)


class ChunkInput(_Record):
    """A fragment ready to be stored: text plus its embedding."""

    ordinal: int = Field(ge=0)
    heading_path: str = ""
    content: str
    embedding: Sequence[float]


class SyncState(_Record):
    cursor: dict[str, Any]
    last_synced_at: datetime


class IngestionRun(_Record):
    job_id: UUID
    trigger: RunTrigger
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    summary: dict[str, Any] | None


class SearchHit(_Record):
    """A fragment found by the hybrid search, with what is needed to cite it."""

    chunk_id: int
    persona_id: str
    document_id: str
    source_type: SourceType
    title: str
    url: str | None
    path: str | None
    section_hint: str | None
    heading_path: str
    content: str
    similarity: float  # cosine similarity with the query: absolute, comparable across searches
    score: float  # Reciprocal Rank Fusion: only orders the hits of one search


class PersonaMatch(_Record):
    """Another persona whose knowledge matches a question (candidate referral, spec HU2)."""

    persona_id: str
    display_name: str
    similarity: float  # best similarity among its hits
    hits: tuple[SearchHit, ...]  # best first
