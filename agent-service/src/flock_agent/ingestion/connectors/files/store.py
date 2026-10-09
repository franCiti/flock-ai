"""Where files live (plan section 5.3): the only part that differs between a local folder and
SharePoint. The cursor is opaque to everyone but the store that produced it."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class FileEntry:
    path: str  # relative to the store root, with "/" separators
    modified_at: datetime
    size: int
    url: str | None = None  # link to the original, when the store has one (SharePoint)
    author: str | None = None


@dataclass(frozen=True)
class FileDelta:
    changed: list[FileEntry]  # new or modified since the cursor
    deleted: list[str]  # paths that existed in the cursor and no longer do
    cursor: dict[str, Any]  # state to pass to the next delta()


class FileStore(Protocol):
    async def delta(self, cursor: dict[str, Any] | None, *, full: bool = False) -> FileDelta:
        """Changes since `cursor`. With full=True every current file is reported as changed
        (deletions are still computed against the cursor)."""
        ...

    async def read_bytes(self, path: str) -> bytes: ...

    def forget(self, cursor: dict[str, Any], path: str) -> dict[str, Any]:
        """A cursor that no longer remembers `path`, so the next delta reports it again."""
        ...
