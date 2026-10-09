"""FileStore over a folder of the disk: the knowledge folder of a persona (plan 5.3, D29)."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flock_agent.ingestion.connectors.files.store import FileDelta, FileEntry

PROFILE_FILE = "persona.md"  # the persona profile (spec HU9.3), never knowledge


def is_ignored(relative_path: str) -> bool:
    """Files that are never knowledge (plan 5.3)."""
    parts = relative_path.split("/")
    return (
        relative_path == PROFILE_FILE
        or any(part.startswith(".") for part in parts)  # hidden files and folders (.git, ...)
        or parts[-1].startswith("~$")  # Office temporary files
    )


class LocalFolderStore:
    """The cursor is a snapshot {path: [modification time in ns, size]} of the folder."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def delta(self, cursor: dict[str, Any] | None, *, full: bool = False) -> FileDelta:
        current = await asyncio.to_thread(self._scan)
        previous: dict[str, list[int]] = (cursor or {}).get("files", {})
        # Compared with the exact integers of the file system: a round trip through a float
        # datetime would lose nanoseconds and report unchanged files as modified.
        snapshot = {path: [mtime_ns, entry.size] for path, (entry, mtime_ns) in current.items()}
        changed = [
            entry
            for path, (entry, _) in sorted(current.items())
            if full or previous.get(path) != snapshot[path]
        ]
        deleted = sorted(path for path in previous if path not in current)
        return FileDelta(changed=changed, deleted=deleted, cursor={"files": snapshot})

    async def read_bytes(self, path: str) -> bytes:
        return await asyncio.to_thread(self._resolve(path).read_bytes)

    def forget(self, cursor: dict[str, Any], path: str) -> dict[str, Any]:
        files = {key: value for key, value in cursor.get("files", {}).items() if key != path}
        return {**cursor, "files": files}

    def _scan(self) -> dict[str, tuple[FileEntry, int]]:
        """Current files with their modification time in nanoseconds."""
        entries: dict[str, tuple[FileEntry, int]] = {}
        if not self._root.is_dir():
            return entries
        for directory, subdirectories, files in os.walk(self._root):  # does not follow links
            subdirectories[:] = [name for name in subdirectories if not name.startswith(".")]
            for name in files:
                absolute = Path(directory) / name
                relative = absolute.relative_to(self._root).as_posix()
                if is_ignored(relative) or absolute.is_symlink():
                    continue  # symbolic links could point outside the persona folder
                stat = absolute.stat()
                entry = FileEntry(
                    path=relative,
                    modified_at=datetime.fromtimestamp(stat.st_mtime_ns / 1e9, UTC),
                    size=stat.st_size,
                )
                entries[relative] = (entry, stat.st_mtime_ns)
        return entries

    def _resolve(self, path: str) -> Path:
        absolute = (self._root / path).resolve()
        if not absolute.is_relative_to(self._root):
            msg = f"path outside the knowledge folder: {path}"
            raise ValueError(msg)
        return absolute
