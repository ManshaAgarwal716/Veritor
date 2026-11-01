"""Tests for PyPI PEP 740 provenance and attestation verification."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.adapters.base import ArtifactHash, ArtifactInfo, PackageMetadata, SourceRepository
from app.provenance.models import ProvenanceStatus
from app.provenance.pypi import PyPIProvenanceChecker
from app.schemas.scans import Ecosystem
from app.source.models import (
    Confidence,
    GitHubRepository,
    MatchMethod,
    MatchStatus,
    SourceMatch,
    UncertainReason,
)

pytestmark = pytest.mark.anyio


def make_metadata(
    name: str = "pkg",
    version: str = "1.0.0",
    sha256_digest: str = "abc",
    manifest: dict | None = None,
) -> PackageMetadata:
    return PackageMetadata(
        ecosystem=Ecosystem.PYPI,
        name=name,
        version=version,
        description="A test package",
        license="MIT",
        homepage="https://example.com",
        repository=SourceRepository(
            declared="https://github.com/org/pkg", url="https://github.com/org/pkg"
        ),
        source_commit=None,
        published_at=datetime.now(UTC),
        dependencies=(),
        scripts={},
        has_install_script=False,
        entry_points={},
        artifacts=(
            ArtifactInfo(
                url="https://files.pythonhosted.org/packages/wheel/pkg-1.0.0.whl",
                filename="pkg-1.0.0.whl",
                hashes=(ArtifactHash(algorithm="sha256", hex_digest=sha256_digest),),
            ),
        ),
        manifest=manifest or {},
    )


async def test_pypi_provenance_unavailable(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    meta = make_metadata(sha256_digest=digest)
    source_match = SourceMatch(
        status=MatchStatus.UNCERTAIN,
        reason=UncertainReason.NO_REPOSITORY,
        confidence=Confidence.NONE,
        method=MatchMethod.NONE,
        explanation="No source",
    )

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.UNAVAILABLE
        assert result.claimed_in_metadata is False
        assert result.integrity_matches is True
        assert "without PyPI PEP 740 digital attestations" in result.explanation


async def test_pypi_provenance_verified(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    commit_sha = "a" * 40

    manifest = {
        "attestations": [
            {
                "publisher": {
                    "repository": "https://github.com/org/pkg",
                    "commit": commit_sha,
                }
            }
        ]
    }

    meta = make_metadata(sha256_digest=digest, manifest=manifest)
    source_match = SourceMatch(
        status=MatchStatus.MATCHED,
        confidence=Confidence.HIGH,
        method=MatchMethod.PACKAGE_TAG,
        explanation="Matched git commit",
        repository=GitHubRepository(owner="org", name="pkg"),
        commit_sha=commit_sha,
    )

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.VERIFIED
        assert result.claimed_in_metadata is True
        assert result.signature_verified is True
        assert result.repository_matches_declared is True
        assert result.commit_matches_source_match is True


async def test_pypi_provenance_invalid(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    commit_sha = "a" * 40

    manifest = {
        "attestations": [
            {
                "invalid": True,
                "publisher": {
                    "repository": "https://github.com/org/pkg",
                    "commit": commit_sha,
                },
            }
        ]
    }

    meta = make_metadata(sha256_digest=digest, manifest=manifest)
    source_match = SourceMatch(
        status=MatchStatus.MATCHED,
        confidence=Confidence.HIGH,
        method=MatchMethod.PACKAGE_TAG,
        explanation="Matched",
        repository=GitHubRepository(owner="org", name="pkg"),
        commit_sha=commit_sha,
    )

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.INVALID
        assert result.claimed_in_metadata is True
        assert result.signature_verified is False
        assert "cryptographic verification" in result.explanation


async def test_pypi_provenance_missing_artifact(tmp_path: Path):
    artifact = tmp_path / "nonexistent.whl"
    meta = make_metadata()
    source_match = SourceMatch(
        status=MatchStatus.UNCERTAIN,
        reason=UncertainReason.NO_REPOSITORY,
        confidence=Confidence.NONE,
        method=MatchMethod.NONE,
        explanation="No source",
    )

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.UNCERTAIN
        assert "Cannot read downloaded artifact" in result.explanation
