"""Common interface of every knowledge source (plan section 5.2, D19).

The ingestion pipeline only knows these types: adding a system means writing a connector.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from flock_agent.ingestion.connectors.files.parsers import ContentFormat
from flock_agent.knowledge.models import SourceType


class SourceDocument(BaseModel):
    """A document as delivered by a source, before redaction and chunking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str  # stable across syncs: "file:<persona>:<path>", "jira:<persona>:<key>"
    persona_id: str
    source_type: SourceType
    source_id: str | None = None  # external source id; None for the persona folder
    parent_id: str | None = None  # email attachment -> its email
    title: str
    url: str | None = None
    path: str | None = None  # relative path, for files
    content: str
    content_format: ContentFormat  # which chunker fits the content
    source_updated_at: datetime


@dataclass(frozen=True)
class SkippedItem:
    """Something of the source that is not indexed, and why (spec HU4.5)."""

    path: str
    reason: str


@dataclass
class SyncPlan:
    """Changes of a source since its last cursor.

    `upserts` is lazy: each document is fetched and parsed only when the pipeline asks for it, so
    a big source never sits in memory. `skipped` fills up while `upserts` is consumed.
    `next_cursor` must be saved only after every upsert and deletion has been applied.
    """

    upserts: AsyncIterator[SourceDocument]
    deleted_ids: list[str]
    next_cursor: dict[str, Any]
    skipped: list[SkippedItem] = field(default_factory=list)


class SourceConnector(Protocol):
    @property
    def source_key(self) -> str:
        """Key of the source: `folder` for the persona folder, otherwise the external source id."""
        ...

    async def sync(self, cursor: dict[str, Any] | None) -> SyncPlan:
        """Changes since `cursor` (None: everything)."""
        ...
