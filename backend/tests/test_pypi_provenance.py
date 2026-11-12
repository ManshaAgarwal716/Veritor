"""Tests for PyPI PEP 740 digital attestations and cryptographic provenance verification."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cryptography.x509
import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ObjectIdentifier

from app.adapters.base import ArtifactHash, ArtifactInfo, PackageMetadata, SourceRepository
from app.provenance.models import ProvenanceStatus
from app.provenance.npm import (
    BundleUnreadableError,
    BundleVerifier,
    SignerIdentity,
    VerificationUnavailableError,
    VerifiedBundle,
)
from app.provenance.pypi import (
    _OID_BUILD_SIGNER_URI,
    _OID_ISSUER_V2,
    _OID_SOURCE_COMMIT,
    _OID_SOURCE_REF,
    _OID_SOURCE_REPOSITORY,
    PyPIProvenanceChecker,
    dsse_pae,
)
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
    manifest: dict[str, Any] | None = None,
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
                url=f"https://files.pythonhosted.org/packages/wheel/{name}-{version}.whl",
                filename=f"{name}-{version}.whl",
                hashes=(ArtifactHash(algorithm="sha256", hex_digest=sha256_digest),),
            ),
        ),
        manifest=manifest or {},
    )


def make_source_match(
    commit_sha: str = "a" * 40,
    repo_owner: str = "org",
    repo_name: str = "pkg",
) -> SourceMatch:
    return SourceMatch(
        status=MatchStatus.MATCHED,
        confidence=Confidence.HIGH,
        method=MatchMethod.PACKAGE_TAG,
        explanation="Matched git commit",
        repository=GitHubRepository(owner=repo_owner, name=repo_name),
        commit_sha=commit_sha,
    )


def _der_utf8(val: str) -> bytes:
    b = val.encode("utf-8")
    return bytes([0x0C, len(b)]) + b


def build_signed_pep740_bundle(
    artifact_name: str,
    artifact_sha256: str,
    repository: str = "https://github.com/org/pkg",
    commit_sha: str = "a" * 40,
    issuer: str = "https://token.actions.githubusercontent.com",
    expired: bool = False,
    corrupt_signature: bool = False,
    mismatched_statement_commit: str | None = None,
    predicate_type: str = "https://docs.pypi.org/attestations/publish/v1",
) -> dict[str, Any]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = cryptography.x509.Name([])
    now = datetime.now(UTC)

    if expired:
        not_before = now - timedelta(days=10)
        not_after = now - timedelta(days=5)
    else:
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(minutes=15)

    builder = (
        cryptography.x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            cryptography.x509.UnrecognizedExtension(
                ObjectIdentifier(_OID_ISSUER_V2), _der_utf8(issuer)
            ),
            critical=False,
        )
        .add_extension(
            cryptography.x509.UnrecognizedExtension(
                ObjectIdentifier(_OID_SOURCE_REPOSITORY), _der_utf8(repository)
            ),
            critical=False,
        )
        .add_extension(
            cryptography.x509.UnrecognizedExtension(
                ObjectIdentifier(_OID_SOURCE_COMMIT), _der_utf8(commit_sha)
            ),
            critical=False,
        )
        .add_extension(
            cryptography.x509.UnrecognizedExtension(
                ObjectIdentifier(_OID_SOURCE_REF), _der_utf8("refs/tags/v1.0.0")
            ),
            critical=False,
        )
        .add_extension(
            cryptography.x509.UnrecognizedExtension(
                ObjectIdentifier(_OID_BUILD_SIGNER_URI),
                _der_utf8(f"{repository}/.github/workflows/release.yml@refs/tags/v1.0.0"),
            ),
            critical=False,
        )
    )
    cert = builder.sign(key, hashes.SHA256())
    cert_der = cert.public_bytes(serialization.Encoding.DER)

    payload_type = "application/vnd.in-toto+json"
    predicate: dict[str, Any] = {}
    if mismatched_statement_commit:
        predicate = {"publisher": {"commit": mismatched_statement_commit}}

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": artifact_name, "digest": {"sha256": artifact_sha256}}],
        "predicateType": predicate_type,
        "predicate": predicate,
    }
    payload_bytes = json.dumps(statement).encode("utf-8")
    pae = dsse_pae(payload_type, payload_bytes)

    if corrupt_signature:
        sig_bytes = b"corrupted_invalid_signature_bytes_32"
    else:
        sig_bytes = key.sign(pae, ec.ECDSA(hashes.SHA256()))

    return {
        "attestations": [
            {
                "version": 1,
                "verification_material": {
                    "certificate": base64.b64encode(cert_der).decode(),
                    "transparency_entries": [],
                },
                "envelope": {
                    "statement": base64.b64encode(payload_bytes).decode(),
                    "signature": base64.b64encode(sig_bytes).decode(),
                    "payloadType": payload_type,
                },
            }
        ]
    }


async def test_pypi_provenance_unavailable(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel content"
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

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.UNAVAILABLE
        assert result.claimed_in_metadata is False
        assert result.integrity_matches is True
        assert "without PyPI PEP 740 digital attestations" in result.explanation


async def test_pypi_provenance_cryptographically_verified(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel content for real verification"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    commit_sha = "a" * 40

    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=digest,
        repository="https://github.com/org/pkg",
        commit_sha=commit_sha,
    )
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle]})
    source_match = make_source_match(commit_sha=commit_sha)

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.VERIFIED
        assert result.claimed_in_metadata is True
        assert result.signature_verified is True
        assert result.tarball_digest_matches is True
        assert result.repository_matches_declared is True
        assert result.commit_matches_source_match is True
        assert result.source_repository == "https://github.com/org/pkg"
        assert result.source_commit == commit_sha
        assert "PyPI PEP 740 attestation verified cryptographically" in result.explanation


async def test_pypi_provenance_tampered_signature_invalid(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"tampered package content"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=digest,
        corrupt_signature=True,
    )
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.INVALID
        assert result.claimed_in_metadata is True
        assert result.signature_verified is False
        assert "signature failed cryptographic verification" in result.explanation


async def test_pypi_provenance_mismatched_digest_invalid(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"legit content on disk"
    artifact.write_bytes(content)
    actual_digest = hashlib.sha256(content).hexdigest()

    # Bundle signed a different digest
    tampered_digest = hashlib.sha256(b"different content").hexdigest()
    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=tampered_digest,
    )
    meta = make_metadata(sha256_digest=actual_digest, manifest={"attestations": [bundle]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.INVALID
        assert result.signature_verified is True
        assert result.tarball_digest_matches is False
        assert "does not match the signed SHA-256 digest" in result.explanation


async def test_pypi_provenance_expired_certificate_invalid(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"package content with expired cert"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=digest,
        expired=True,
    )
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.INVALID
        assert "expired" in result.explanation.lower()


async def test_pypi_provenance_untrusted_issuer_invalid(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"package content with untrusted issuer"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=digest,
        issuer="https://evil-untrusted-issuer.example.com",
    )
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.INVALID
        assert "identity provider is not recognized" in result.explanation


async def test_pypi_provenance_unverified_metadata_is_not_verified(tmp_path: Path):
    """Security check: Do not trust unverified bundle fields without cryptographic signatures."""
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    # Manifest claims publisher identity, but has NO cryptographic verification material
    manifest = {
        "attestations": [
            {
                "publisher": {
                    "repository": "https://github.com/org/pkg",
                    "commit": "a" * 40,
                }
            }
        ]
    }
    meta = make_metadata(sha256_digest=digest, manifest=manifest)
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        # Must NOT be marked VERIFIED
        assert result.status is ProvenanceStatus.NOT_VERIFIED
        assert result.claimed_in_metadata is True
        assert result.signature_verified is False
        assert "contains no cryptographic signatures" in result.explanation


async def test_pypi_provenance_mock_verifier(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    commit_sha = "b" * 40

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "pkg-1.0.0.whl", "digest": {"sha256": digest}}],
        "predicateType": "https://docs.pypi.org/attestations/publish/v1",
        "predicate": {},
    }

    class MockVerifier(BundleVerifier):
        def verify(self, bundle_data: Any) -> VerifiedBundle:
            return VerifiedBundle(
                payload_type="application/vnd.in-toto+json",
                payload=json.dumps(statement).encode("utf-8"),
                identity=SignerIdentity(
                    issuer="https://token.actions.githubusercontent.com",
                    source_repository="https://github.com/org/pkg",
                    source_commit=commit_sha,
                    source_ref="refs/tags/v1.0.0",
                    build_workflow="https://github.com/org/pkg/.github/workflows/release.yml@refs/tags/v1.0.0",
                ),
            )

    bundle_dict = {
        "verification_material": {"dummy": True},
        "envelope": {"dummy": True},
    }
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle_dict]})
    source_match = make_source_match(commit_sha=commit_sha)

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client, verifier=MockVerifier())
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.VERIFIED
        assert result.claimed_in_metadata is True
        assert result.signature_verified is True
        assert result.source_commit == commit_sha


async def test_pypi_provenance_verification_unavailable(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    class OfflineVerifier(BundleVerifier):
        def verify(self, bundle_data: Any) -> VerifiedBundle:
            raise VerificationUnavailableError("Could not load Sigstore trust root metadata")

    bundle_dict = {
        "verification_material": {"dummy": True},
        "envelope": {"dummy": True},
    }
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle_dict]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client, verifier=OfflineVerifier())
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.NOT_VERIFIED
        assert "could not be verified" in result.explanation


async def test_pypi_provenance_bundle_unreadable_uncertain(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"sample wheel"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    class CorruptBundleVerifier(BundleVerifier):
        def verify(self, bundle_data: Any) -> VerifiedBundle:
            raise BundleUnreadableError("Malformed JSON in DSSE envelope")

    bundle_dict = {
        "verification_material": {"dummy": True},
        "envelope": {"dummy": True},
    }
    meta = make_metadata(sha256_digest=digest, manifest={"attestations": [bundle_dict]})
    source_match = make_source_match()

    async with httpx.AsyncClient() as client:
        checker = PyPIProvenanceChecker(client, verifier=CorruptBundleVerifier())
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.UNCERTAIN
        assert "could not be read" in result.explanation


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


async def test_pypi_provenance_remote_integrity_api_fetch(tmp_path: Path):
    artifact = tmp_path / "pkg-1.0.0.whl"
    content = b"remote fetched artifact bytes"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    commit_sha = "c" * 40

    bundle = build_signed_pep740_bundle(
        artifact_name="pkg-1.0.0.whl",
        artifact_sha256=digest,
        commit_sha=commit_sha,
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "integrity/pkg/1.0.0/pkg-1.0.0.whl/provenance" in str(request.url):
            return httpx.Response(
                200,
                json={"version": 1, "attestation_bundles": [bundle]},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    meta = make_metadata(sha256_digest=digest, manifest={})  # Empty manifest, must query remote API
    source_match = make_source_match(commit_sha=commit_sha)

    async with httpx.AsyncClient(transport=transport) as client:
        checker = PyPIProvenanceChecker(client)
        result = await checker.check(meta, artifact, source_match)

        assert result.status is ProvenanceStatus.VERIFIED
        assert result.signature_verified is True
        assert result.tarball_digest_matches is True
        assert result.source_commit == commit_sha
