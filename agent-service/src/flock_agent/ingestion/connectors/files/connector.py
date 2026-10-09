"""SourceConnector for files, over any FileStore: a persona folder or SharePoint (plan 5.3)."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any

from flock_agent.ingestion.connectors.base import SkippedItem, SourceDocument, SyncPlan
from flock_agent.ingestion.connectors.files.parsers import (
    PARSERS_VERSION,
    SkipFileError,
    parse_file,
)
from flock_agent.ingestion.connectors.files.store import FileEntry, FileStore
from flock_agent.knowledge.models import SourceType

log = logging.getLogger(__name__)

FOLDER_SOURCE_KEY = "folder"


class FilesConnector:
    """Turns the changes of a FileStore into SourceDocuments.

    The cursor wraps the store cursor with the parsers version: when parsing improves (e.g. a new
    file type), every file is read again, while deletions are still detected.
    """

    def __init__(
        self,
        persona_id: str,
        store: FileStore,
        *,
        max_bytes: int,
        source_id: str | None = None,
        source_type: SourceType = "file",
    ) -> None:
        self._persona_id = persona_id
        self._store = store
        self._max_bytes = max_bytes
        self._source_id = source_id
        self._source_type = source_type

    @property
    def source_key(self) -> str:
        return self._source_id or FOLDER_SOURCE_KEY

    def document_id(self, path: str) -> str:
        if self._source_id is None:
            return f"{self._source_type}:{self._persona_id}:{path}"
        return f"{self._source_type}:{self._persona_id}:{self._source_id}:{path}"

    async def sync(self, cursor: dict[str, Any] | None) -> SyncPlan:
        cursor = cursor or {}
        same_parsers = cursor.get("parsers_version") == PARSERS_VERSION
        delta = await self._store.delta(cursor.get("store"), full=not same_parsers)
        skipped: list[SkippedItem] = []
        next_cursor = {"parsers_version": PARSERS_VERSION, "store": delta.cursor}
        return SyncPlan(
            upserts=self._documents(delta.changed, skipped, next_cursor),
            deleted_ids=[self.document_id(path) for path in delta.deleted],
            next_cursor=next_cursor,
            skipped=skipped,
        )

    async def _documents(
        self, entries: list[FileEntry], skipped: list[SkippedItem], next_cursor: dict[str, Any]
    ) -> AsyncIterator[SourceDocument]:
        """Read and parse each file; `skipped` and `next_cursor` are those of the SyncPlan."""
        for entry in entries:
            try:
                data = await self._store.read_bytes(entry.path)
                parsed = await asyncio.to_thread(
                    parse_file, entry.path, data, max_bytes=self._max_bytes
                )
            except SkipFileError as skip:
                # Remembered in the cursor: not read again until the file or the parsers change.
                skipped.append(SkippedItem(entry.path, skip.reason))
                continue
            except OSError as error:
                # Probably transient (file locked, removed while syncing): retried next time.
                log.warning("could not read file", extra={"path": entry.path, "error": str(error)})
                skipped.append(SkippedItem(entry.path, f"could not be read ({error})"))
                next_cursor["store"] = self._store.forget(next_cursor["store"], entry.path)
                continue
            yield SourceDocument(
                id=self.document_id(entry.path),
                persona_id=self._persona_id,
                source_type=self._source_type,
                source_id=self._source_id,
                title=parsed.title or PurePosixPath(entry.path).stem,
                url=entry.url,
                path=entry.path,
                content=parsed.text,
                content_format=parsed.content_format,
                source_updated_at=entry.modified_at,
            )
