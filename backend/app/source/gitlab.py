"""Match a published package version to an exact commit in its GitLab repository.

Addresses audit finding FEAT-03:
Enables source repository discovery, candidate tag matching, and commit archive retrieval
for GitLab-hosted packages (gitlab.com).
"""

from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from app.adapters.base import PackageMetadata
from app.adapters.errors import (
    AdapterError,
    InvalidRegistryResponseError,
    RegistryNotFoundError,
)
from app.adapters.http import RegistryLimits, download_unhashed, fetch_bytes
from app.source.base import SourceNotMatchedError
from app.source.github import (
    _COMMIT_SHA,
    _DEFAULT_BRANCH,
    _PEELED_SUFFIX,
    _SERVICE_HEADER,
    _TAG_METHODS,
    RepositoryRefs,
    TagKind,
    _iter_packets,
    _matched,
    _uncertain,
    candidate_tags,
)
from app.source.models import (
    Confidence,
    GitLabRepository,
    MatchMethod,
    MatchStatus,
    SourceArchive,
    SourceMatch,
    UncertainReason,
)

GITLAB_HOSTS = {"gitlab.com", "www.gitlab.com"}
ARCHIVE_BASE = "https://gitlab.com"


def parse_gitlab_repository(url: str) -> GitLabRepository | None:
    """Return owner and repository name from an https GitLab URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname not in GITLAB_HOSTS:
        return None
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2:
        return None
    # Support group/subgroup.../project
    name = segments[-1].removesuffix(".git")
    owner = "/".join(segments[:-1])
    try:
        return GitLabRepository(owner=owner, name=name)
    except ValidationError:
        return None


def _parse_gitlab_refs(body: bytes) -> RepositoryRefs:
    """Parse git upload-pack advertisement packet stream into tags and branch tips."""
    tags: dict[str, str] = {}
    branch_tips: set[str] = set()
    default_branch: str | None = None
    packets = _iter_packets(body)
    if next(packets, None) != _SERVICE_HEADER:
        raise InvalidRegistryResponseError("Not a git reference advertisement")

    for packet in packets:
        line, _, capabilities = packet.rstrip(b"\n").partition(b"\0")
        if capabilities and (symref := _DEFAULT_BRANCH.search(capabilities)):
            default_branch = symref.group(1).decode(errors="replace")
        sha_bytes, _, ref_bytes = line.partition(b" ")
        sha = sha_bytes.decode(errors="replace")
        ref = ref_bytes.decode(errors="replace")
        if not _COMMIT_SHA.fullmatch(sha) or not ref:
            raise InvalidRegistryResponseError("Malformed git reference")

        if ref.startswith("refs/heads/"):
            branch_tips.add(sha)
        elif ref.startswith("refs/tags/"):
            tags[ref.removeprefix("refs/tags/").removesuffix(_PEELED_SUFFIX)] = sha
    return RepositoryRefs(tags, frozenset(branch_tips), default_branch)


class GitLabSourceResolver:
    """Resolves and retrieves source archives for GitLab-hosted packages."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        limits: RegistryLimits | None = None,
        token: SecretStr | None = None,
    ) -> None:
        self._client = client
        self._limits = limits or RegistryLimits()
        self._token = token

    def can_handle(self, url: str) -> bool:
        """Return True if the URL points to a recognized GitLab repository."""
        return parse_gitlab_repository(url) is not None

    async def resolve(self, metadata: PackageMetadata) -> SourceMatch:
        """Find the exact commit for a package version from GitLab."""
        declared = metadata.repository
        if declared is None:
            return _uncertain(
                UncertainReason.NO_REPOSITORY, "The package does not declare a repository."
            )
        directory = declared.directory
        repository = parse_gitlab_repository(declared.url) if declared.url else None
        if repository is None:
            return _uncertain(
                UncertainReason.UNSUPPORTED_HOST,
                "The declared repository is not a recognized GitLab repository.",
                directory=directory,
            )

        candidates = candidate_tags(metadata.name, metadata.version, directory)
        recorded = (metadata.source_commit or "").lower()
        recorded_commit = recorded if _COMMIT_SHA.fullmatch(recorded) else None
        shared: dict[str, object] = {
            "repository": repository,
            "directory": directory,
            "recorded_commit": recorded_commit,
            "tags_checked": tuple(candidates),
        }

        try:
            refs = await self._fetch_refs(repository)
        except RegistryNotFoundError:
            return _uncertain(
                UncertainReason.REPOSITORY_NOT_FOUND,
                "The declared GitLab repository does not exist or is private.",
                **shared,
            )
        except AdapterError as exc:
            return _uncertain(
                UncertainReason.LOOKUP_FAILED,
                f"Could not read GitLab repository tags: {exc}",
                **shared,
            )

        found = {tag: refs.tags[tag] for tag in candidates if tag in refs.tags}
        shared["tags_found"] = found

        if recorded_commit is not None:
            matching_tags = [tag for tag, sha in found.items() if sha == recorded_commit]
            if matching_tags:
                tag = matching_tags[0]
                kind = candidates[tag]
                return _matched(
                    MatchMethod.RECORDED_COMMIT_AND_TAG,
                    Confidence.HIGH,
                    f"Tag {tag} matches this version and confirms the recorded commit.",
                    commit_sha=recorded_commit,
                    tag=tag,
                    **shared,
                )
            if recorded_commit in refs.branch_tips or recorded_commit in refs.tags.values():
                return _matched(
                    MatchMethod.RECORDED_COMMIT,
                    Confidence.LOW,
                    "The package recorded a valid commit in the GitLab repository, "
                    "but no tag confirmed it.",
                    commit_sha=recorded_commit,
                    **shared,
                )
            if found:
                return _uncertain(
                    UncertainReason.RECORDED_COMMIT_CONFLICTS_WITH_TAG,
                    "The package recorded a commit that does not match the tag for this version.",
                    **shared,
                )
            return _uncertain(
                UncertainReason.RECORDED_COMMIT_UNVERIFIED,
                "The package recorded a commit that is not reachable on any branch or tag.",
                **shared,
            )

        # Match tags only
        if not found:
            return _uncertain(
                UncertainReason.NO_MATCHING_TAG,
                "The package recorded no commit, and no GitLab tag matches this version.",
                **shared,
            )
        if len(set(found.values())) > 1:
            return _uncertain(
                UncertainReason.AMBIGUOUS_TAGS,
                "GitLab tags matching this version point to different commits.",
                **shared,
            )

        tag = next(iter(found))
        kind = candidates[tag]
        confidence = Confidence.MEDIUM
        explanation = (
            f"GitLab tag {tag} matches this version. The package recorded no commit to confirm it."
        )
        if kind is TagKind.RELEASE_PREFIX:
            confidence = Confidence.LOW
        elif kind is TagKind.VERSION and directory:
            confidence = Confidence.LOW
            explanation += " The tag is not specific to this package within a monorepo."

        return _matched(
            _TAG_METHODS[kind],
            confidence,
            explanation,
            commit_sha=found[tag],
            tag=tag,
            **shared,
        )

    async def _fetch_refs(self, repository: GitLabRepository) -> RepositoryRefs:
        headers = {}
        if self._token is not None and self._token.get_secret_value():
            headers["PRIVATE-TOKEN"] = self._token.get_secret_value()
        url = (
            f"{ARCHIVE_BASE}/{repository.owner}/{repository.name}.git/info/refs"
            "?service=git-upload-pack"
        )
        body = await fetch_bytes(self._client, url, self._limits, headers=headers)
        return _parse_gitlab_refs(body)

    async def download_source(self, match: SourceMatch, destination_dir: Path) -> SourceArchive:
        """Download exact commit archive from GitLab."""
        if (
            match.status is not MatchStatus.MATCHED
            or match.repository is None
            or match.commit_sha is None
        ):
            raise SourceNotMatchedError(f"No source commit was established: {match.explanation}")

        repository, commit = match.repository, match.commit_sha
        # GitLab commit archive route
        archive_url = (
            f"{ARCHIVE_BASE}/{repository.owner}/{repository.name}/-/archive/{commit}/"
            f"{repository.name}-{commit}.tar.gz"
        )
        download = await download_unhashed(
            self._client,
            archive_url,
            f"{repository.name}-{commit}.tar.gz",
            destination_dir,
            self._limits,
        )
        return SourceArchive(
            repository=repository,
            commit_sha=commit,
            path=download.path,
            size_bytes=download.size_bytes,
            sha256=download.sha256,
        )
