"""Read extracted files through their inventory, confirming each still matches its hash."""

import hashlib
import os
import posixpath

from app.archives.models import EntryKind, FileInventory, InventoryEntry


class ComparisonIntegrityError(Exception):
    """An extracted file no longer matches its inventory entry."""


def normalize_relative(path: str) -> str | None:
    """Return a clean relative path. The root is an empty string, and escapes return None."""
    cleaned = path.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or "\0" in cleaned:
        return None
    normalized = posixpath.normpath(cleaned)
    if normalized == "..":
        return None
    if normalized.startswith("../"):
        return None
    return "" if normalized == "." else normalized


def is_within(path: str, directory: str) -> bool:
    return path.startswith(f"{directory}/")


DEFAULT_MAX_CACHE_ITEMS = 512
DEFAULT_MAX_CACHED_FILE_SIZE = 512 * 1024  # 512 KB


class FileTree:
    """A view of an inventory, optionally limited to one subdirectory."""

    def __init__(
        self,
        inventory: FileInventory,
        directory: str = "",
        cache: dict[str, bytes] | None = None,
        max_cache_items: int = DEFAULT_MAX_CACHE_ITEMS,
        max_cached_file_size: int = DEFAULT_MAX_CACHED_FILE_SIZE,
    ) -> None:
        self._inventory = inventory
        self.directory = directory
        prefix = f"{directory}/" if directory else ""
        self.entries: dict[str, InventoryEntry] = {
            entry.path.removeprefix(prefix): entry
            for entry in inventory.entries
            if entry.path.startswith(prefix)
        }
        self._cache = cache if cache is not None else {}
        self.max_cache_items = max_cache_items
        self.max_cached_file_size = max_cached_file_size
        self._reads_from_cache = 0
        self._reads_from_disk = 0

    @property
    def cache_hits(self) -> int:
        """Return the number of cache hits on this tree."""
        return self._reads_from_cache

    @property
    def disk_reads(self) -> int:
        """Return the number of disk reads on this tree."""
        return self._reads_from_disk

    def read(self, path: str, max_bytes: int) -> bytes | None:
        """Return a regular file's bytes, or None if it is absent, not regular or too large."""
        entry = self.entries.get(path)
        if entry is None or entry.kind is not EntryKind.REGULAR or entry.size_bytes > max_bytes:
            return None

        # Check cache by entry's canonical path in the underlying inventory
        canonical_path = entry.path
        if canonical_path in self._cache:
            data = self._cache[canonical_path]
            if len(data) > max_bytes:
                return None
            self._reads_from_cache += 1
            return data

        target = self._inventory.root.joinpath(*entry.path.split("/"))
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as file:
            data = file.read(max_bytes + 1)
        if hashlib.sha256(data).hexdigest() != entry.sha256:
            raise ComparisonIntegrityError(f"Extracted file changed: {entry.path!r}")

        self._reads_from_disk += 1
        if len(data) <= self.max_cached_file_size and len(self._cache) < self.max_cache_items:
            self._cache[canonical_path] = data

        return data
