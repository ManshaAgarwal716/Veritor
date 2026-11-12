"""Multi-host source resolution and archive retrieval dispatcher.

Addresses audit finding FEAT-03:
Dispatches source resolution requests to host-specific adapters (GitHub, GitLab, Bitbucket),
returning UNSUPPORTED_HOST or UNCERTAIN honestly when repository sources cannot be verified.
"""

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from app.adapters.base import PackageMetadata
from app.adapters.http import RegistryLimits
from app.source.base import SourceHostAdapter, SourceNotMatchedError
from app.source.bitbucket import BitbucketSourceResolver
from app.source.github import GitHubSourceResolver, _uncertain
from app.source.gitlab import GitLabSourceResolver
from app.source.models import (
    BitbucketRepository,
    GitLabRepository,
    MatchStatus,
    SourceArchive,
    SourceHost,
    SourceMatch,
    UncertainReason,
)


class MultiHostSourceResolver:
    """Dispatches package source discovery across GitHub, GitLab, and Bitbucket hosts."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        limits: RegistryLimits | None = None,
        github_token: SecretStr | None = None,
        gitlab_token: SecretStr | None = None,
        bitbucket_token: SecretStr | None = None,
        custom_adapters: Sequence[SourceHostAdapter] | None = None,
    ) -> None:
        self._client = client
        self._limits = limits or RegistryLimits()
        self.github = GitHubSourceResolver(client, limits=self._limits, token=github_token)
        self.gitlab = GitLabSourceResolver(client, limits=self._limits, token=gitlab_token)
        self.bitbucket = BitbucketSourceResolver(client, limits=self._limits, token=bitbucket_token)

        self._adapters: list[SourceHostAdapter] = [
            *(custom_adapters or []),
            self.github,
            self.gitlab,
            self.bitbucket,
        ]

    def can_handle(self, url: str) -> bool:
        """Return True if any registered adapter can handle the repository URL."""
        return any(adapter.can_handle(url) for adapter in self._adapters)

    async def resolve(self, metadata: PackageMetadata) -> SourceMatch:
        """Find the matching commit for a package version across supported hosts."""
        declared = metadata.repository
        if declared is None or not declared.url:
            return _uncertain(
                UncertainReason.NO_REPOSITORY, "The package does not declare a repository."
            )

        url = declared.url.strip()
        directory = declared.directory

        for adapter in self._adapters:
            if adapter.can_handle(url):
                return await adapter.resolve(metadata)

        # Unrecognized host: return UNSUPPORTED_HOST honestly
        try:
            hostname = urlsplit(url).hostname or url
        except Exception:
            hostname = url

        return _uncertain(
            UncertainReason.UNSUPPORTED_HOST,
            f"The declared repository host '{hostname}' is not supported.",
            directory=directory,
        )

    async def download_source(self, match: SourceMatch, destination_dir: Path) -> SourceArchive:
        """Download and verify the commit archive using the appropriate host adapter."""
        if (
            match.status is not MatchStatus.MATCHED
            or match.repository is None
            or match.commit_sha is None
        ):
            raise SourceNotMatchedError(f"No source commit was established: {match.explanation}")

        repo = match.repository
        if isinstance(repo, GitLabRepository) or getattr(repo, "host", None) == SourceHost.GITLAB:
            return await self.gitlab.download_source(match, destination_dir)
        if (
            isinstance(repo, BitbucketRepository)
            or getattr(repo, "host", None) == SourceHost.BITBUCKET
        ):
            return await self.bitbucket.download_source(match, destination_dir)
        return await self.github.download_source(match, destination_dir)
