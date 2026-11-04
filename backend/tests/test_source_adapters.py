"""Tests for multi-host source adapters (GitHub, GitLab, Bitbucket).

Addresses audit finding FEAT-03:
1. SourceHostAdapter protocol conformance.
2. GitLab repository parsing, git upload-pack refs matching, and archive download.
3. Bitbucket repository parsing, refs matching, and archive download.
4. MultiHostSourceResolver host dispatching and honest UNSUPPORTED_HOST handling.
"""

from pathlib import Path

import httpx
import pytest

from app.adapters.base import PackageMetadata, SourceRepository
from app.schemas.scans import Ecosystem
from app.source import (
    BitbucketRepository,
    BitbucketSourceResolver,
    Confidence,
    GitHubRepository,
    GitHubSourceResolver,
    GitLabRepository,
    GitLabSourceResolver,
    MatchMethod,
    MatchStatus,
    MultiHostSourceResolver,
    SourceHostAdapter,
    SourceMatch,
    SourceNotMatchedError,
    UncertainReason,
    parse_bitbucket_repository,
    parse_gitlab_repository,
)

pytestmark = pytest.mark.anyio

COMMIT_1 = "1111111111111111111111111111111111111111"
COMMIT_2 = "2222222222222222222222222222222222222222"


def _packet(payload: bytes) -> bytes:
    """Format a git pkt-line packet."""
    length = len(payload) + 4
    return f"{length:04x}".encode("ascii") + payload


def _make_meta(
    name: str = "demo-pkg",
    version: str = "1.0.0",
    repo_url: str | None = None,
    source_commit: str | None = None,
    directory: str | None = None,
) -> PackageMetadata:
    return PackageMetadata(
        ecosystem=Ecosystem.NPM,
        name=name,
        version=version,
        description=None,
        license=None,
        homepage=None,
        repository=SourceRepository(declared=repo_url or "", url=repo_url, directory=directory)
        if repo_url
        else None,
        source_commit=source_commit,
        published_at=None,
        dependencies=(),
        scripts={},
        has_install_script=False,
        entry_points={},
        artifacts=(),
        manifest={},
    )


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


def test_source_host_adapter_protocol_conformance() -> None:
    client = httpx.AsyncClient()
    gh = GitHubSourceResolver(client)
    gl = GitLabSourceResolver(client)
    bb = BitbucketSourceResolver(client)
    multi = MultiHostSourceResolver(client)

    assert isinstance(gh, SourceHostAdapter)
    assert isinstance(gl, SourceHostAdapter)
    assert isinstance(bb, SourceHostAdapter)
    assert isinstance(multi, SourceHostAdapter)


# ---------------------------------------------------------------------------
# URL Parsing
# ---------------------------------------------------------------------------


def test_parse_gitlab_repository() -> None:
    assert parse_gitlab_repository("https://gitlab.com/owner/project") == GitLabRepository(
        owner="owner", name="project"
    )
    assert parse_gitlab_repository("https://gitlab.com/owner/project.git") == GitLabRepository(
        owner="owner", name="project"
    )
    assert parse_gitlab_repository(
        "https://gitlab.com/group/subgroup/project.git"
    ) == GitLabRepository(owner="group/subgroup", name="project")
    assert parse_gitlab_repository("https://github.com/owner/project") is None
    assert parse_gitlab_repository("not-a-url") is None
    assert parse_gitlab_repository("https://gitlab.com/single") is None


def test_parse_bitbucket_repository() -> None:
    assert parse_bitbucket_repository("https://bitbucket.org/owner/repo") == BitbucketRepository(
        owner="owner", name="repo"
    )
    assert parse_bitbucket_repository(
        "https://bitbucket.org/owner/repo.git"
    ) == BitbucketRepository(owner="owner", name="repo")
    assert parse_bitbucket_repository("https://github.com/owner/repo") is None
    assert parse_bitbucket_repository("not-a-url") is None
    assert parse_bitbucket_repository("https://bitbucket.org/single") is None


# ---------------------------------------------------------------------------
# GitLabSourceResolver Tests
# ---------------------------------------------------------------------------


async def test_gitlab_resolve_matching_tag() -> None:
    refs_body = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_1} refs/tags/v1.0.0\n".encode())
        + _packet(f"{COMMIT_2} refs/heads/main\n".encode())
        + b"0000"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "info/refs" in str(request.url):
            return httpx.Response(200, content=refs_body)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = GitLabSourceResolver(client)

    meta = _make_meta(repo_url="https://gitlab.com/acme/lib", version="1.0.0")
    match = await resolver.resolve(meta)

    assert match.status is MatchStatus.MATCHED
    assert match.commit_sha == COMMIT_1
    assert match.tag == "v1.0.0"
    assert match.confidence is Confidence.MEDIUM
    assert match.method is MatchMethod.VERSION_TAG
    assert match.repository == GitLabRepository(owner="acme", name="lib")


async def test_gitlab_resolve_recorded_commit_and_tag() -> None:
    refs_body = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_1} refs/tags/v1.0.0\n".encode())
        + _packet(f"{COMMIT_1} refs/heads/main\n".encode())
        + b"0000"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=refs_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = GitLabSourceResolver(client)

    meta = _make_meta(
        repo_url="https://gitlab.com/acme/lib",
        version="1.0.0",
        source_commit=COMMIT_1,
    )
    match = await resolver.resolve(meta)

    assert match.status is MatchStatus.MATCHED
    assert match.commit_sha == COMMIT_1
    assert match.confidence is Confidence.HIGH
    assert match.method is MatchMethod.RECORDED_COMMIT_AND_TAG


async def test_gitlab_resolve_no_matching_tag() -> None:
    refs_body = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_1} refs/tags/v2.0.0\n".encode())
        + b"0000"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=refs_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = GitLabSourceResolver(client)

    meta = _make_meta(repo_url="https://gitlab.com/acme/lib", version="1.0.0")
    match = await resolver.resolve(meta)

    assert match.status is MatchStatus.UNCERTAIN
    assert match.reason is UncertainReason.NO_MATCHING_TAG


async def test_gitlab_resolve_not_found_repository() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = GitLabSourceResolver(client)

    meta = _make_meta(repo_url="https://gitlab.com/nonexistent/missing", version="1.0.0")
    match = await resolver.resolve(meta)

    assert match.status is MatchStatus.UNCERTAIN
    assert match.reason is UncertainReason.REPOSITORY_NOT_FOUND


async def test_gitlab_download_source(tmp_path: Path) -> None:
    tarball_bytes = b"\x1f\x8b\x08mock_gitlab_tarball_content"

    def handler(request: httpx.Request) -> httpx.Response:
        if "archive" in str(request.url):
            return httpx.Response(200, stream=httpx.ByteStream(tarball_bytes))
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = GitLabSourceResolver(client)

    repo = GitLabRepository(owner="acme", name="lib")
    match = SourceMatch(
        status=MatchStatus.MATCHED,
        method=MatchMethod.VERSION_TAG,
        confidence=Confidence.MEDIUM,
        explanation="Matched GitLab tag",
        repository=repo,
        commit_sha=COMMIT_1,
    )

    archive = await resolver.download_source(match, tmp_path)
    assert archive.repository == repo
    assert archive.commit_sha == COMMIT_1
    assert archive.size_bytes == len(tarball_bytes)
    assert archive.path.exists()


# ---------------------------------------------------------------------------
# BitbucketSourceResolver Tests
# ---------------------------------------------------------------------------


async def test_bitbucket_resolve_matching_tag() -> None:
    refs_body = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_1} refs/tags/1.0.0\n".encode())
        + b"0000"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=refs_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = BitbucketSourceResolver(client)

    meta = _make_meta(repo_url="https://bitbucket.org/org/pkg", version="1.0.0")
    match = await resolver.resolve(meta)

    assert match.status is MatchStatus.MATCHED
    assert match.commit_sha == COMMIT_1
    assert match.repository == BitbucketRepository(owner="org", name="pkg")


async def test_bitbucket_download_source(tmp_path: Path) -> None:
    tarball_bytes = b"\x1f\x8b\x08mock_bitbucket_tarball_content"

    def handler(request: httpx.Request) -> httpx.Response:
        if "get" in str(request.url):
            return httpx.Response(200, stream=httpx.ByteStream(tarball_bytes))
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = BitbucketSourceResolver(client)

    repo = BitbucketRepository(owner="org", name="pkg")
    match = SourceMatch(
        status=MatchStatus.MATCHED,
        method=MatchMethod.VERSION_TAG,
        confidence=Confidence.MEDIUM,
        explanation="Matched Bitbucket tag",
        repository=repo,
        commit_sha=COMMIT_1,
    )

    archive = await resolver.download_source(match, tmp_path)
    assert archive.repository == repo
    assert archive.commit_sha == COMMIT_1
    assert archive.size_bytes == len(tarball_bytes)
    assert archive.path.exists()


# ---------------------------------------------------------------------------
# MultiHostSourceResolver Dispatching & Honest UNSUPPORTED_HOST Tests
# ---------------------------------------------------------------------------


async def test_multi_host_dispatches_correctly() -> None:
    gh_refs = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_1} refs/tags/v1.0.0\n".encode())
        + b"0000"
    )
    gl_refs = (
        _packet(b"# service=git-upload-pack\n")
        + b"0000"
        + _packet(f"{COMMIT_2} refs/tags/v1.0.0\n".encode())
        + b"0000"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "github.com" in url:
            return httpx.Response(200, content=gh_refs)
        if "gitlab.com" in url:
            return httpx.Response(200, content=gl_refs)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    multi = MultiHostSourceResolver(client)

    # 1. GitHub package
    meta_gh = _make_meta(repo_url="https://github.com/acme/pkg", version="1.0.0")
    match_gh = await multi.resolve(meta_gh)
    assert match_gh.status is MatchStatus.MATCHED
    assert match_gh.commit_sha == COMMIT_1
    assert isinstance(match_gh.repository, GitHubRepository)

    # 2. GitLab package
    meta_gl = _make_meta(repo_url="https://gitlab.com/acme/pkg", version="1.0.0")
    match_gl = await multi.resolve(meta_gl)
    assert match_gl.status is MatchStatus.MATCHED
    assert match_gl.commit_sha == COMMIT_2
    assert isinstance(match_gl.repository, GitLabRepository)

    # 3. Unsupported Host (e.g. sourceforge or custom internal)
    meta_sf = _make_meta(repo_url="https://sourceforge.net/projects/foobar", version="1.0.0")
    match_sf = await multi.resolve(meta_sf)
    assert match_sf.status is MatchStatus.UNCERTAIN
    assert match_sf.reason is UncertainReason.UNSUPPORTED_HOST
    assert "sourceforge.net" in match_sf.explanation

    # 4. No repository
    meta_none = _make_meta(repo_url=None, version="1.0.0")
    match_none = await multi.resolve(meta_none)
    assert match_none.status is MatchStatus.UNCERTAIN
    assert match_none.reason is UncertainReason.NO_REPOSITORY


async def test_download_source_unmatched_raises(tmp_path: Path) -> None:
    client = httpx.AsyncClient()
    multi = MultiHostSourceResolver(client)
    uncertain_match = SourceMatch(
        status=MatchStatus.UNCERTAIN,
        reason=UncertainReason.UNSUPPORTED_HOST,
        explanation="Unsupported host",
    )
    with pytest.raises(SourceNotMatchedError):
        await multi.download_source(uncertain_match, tmp_path)
