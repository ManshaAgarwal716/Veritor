"""Source host adapter interfaces and protocols.

Addresses audit finding FEAT-03:
Defines the pluggable adapter protocol for source hosts (GitHub, GitLab, Bitbucket),
enabling multi-host repository discovery, tag resolution, and commit archive retrieval.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.adapters.base import PackageMetadata
from app.adapters.errors import AdapterError
from app.source.models import SourceArchive, SourceMatch


class SourceNotMatchedError(AdapterError):
    """Source was requested for a result that did not establish an exact commit."""


@runtime_checkable
class SourceHostAdapter(Protocol):
    """Adapter interface for a code hosting platform."""

    def can_handle(self, url: str) -> bool:
        """Return True if this adapter can resolve and retrieve sources for the given URL."""
        ...

    async def resolve(self, metadata: PackageMetadata) -> SourceMatch:
        """Attempt to match a package version to an exact commit in its repository."""
        ...

    async def download_source(self, match: SourceMatch, destination_dir: Path) -> SourceArchive:
        """Download and verify the source archive for the exact matched commit."""
        ...
