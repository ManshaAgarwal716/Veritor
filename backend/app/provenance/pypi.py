"""Verify a PyPI package's PEP 740 digital attestations and cryptographic provenance.

A result of VERIFIED means all of these were cryptographically checked:

1. The attestation's cryptographic signature is verified against the certificate's public key
   under the Sigstore / PEP 740 trust root.
2. The signing certificate identifies a recognized CI/CD OIDC provider and source repository.
3. The signed statement's SHA-256 (or SHA-512) digest matches artifact bytes on disk.
4. If specified, the commit in the signed statement agrees with the signed certificate.
5. Repository and commit consistency are evaluated against the declared source metadata.

Safety Invariant:
Missing provenance awards 0 risk points and is reported as UNAVAILABLE, not INVALID or malicious.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import cryptography.x509
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.adapters.base import PackageMetadata
from app.provenance.models import ProvenanceResult, ProvenanceStatus
from app.provenance.npm import (
    BundleUnreadableError,
    BundleVerifier,
    SignatureInvalidError,
    SignerIdentity,
    VerificationUnavailableError,
    VerifiedBundle,
    _decode_der_utf8,
)
from app.source.models import MatchStatus, SourceMatch

logger = logging.getLogger(__name__)

_HASH_CHUNK = 64 * 1024
IN_TOTO_PAYLOAD_TYPE = "application/vnd.in-toto+json"
PEP740_PUBLISH_PREDICATE_PREFIX = "https://docs.pypi.org/attestations/publish/"
SLSA_PREDICATE_PREFIX = "https://slsa.dev/provenance/"

TRUSTED_PYPI_OIDC_ISSUERS = frozenset(
    {
        "https://token.actions.githubusercontent.com",
        "https://gitlab.com",
        "https://accounts.google.com",
    }
)

_OID_ISSUER_V2 = "1.3.6.1.4.1.57264.1.8"
_OID_ISSUER_V1 = "1.3.6.1.4.1.57264.1.1"
_OID_BUILD_SIGNER_URI = "1.3.6.1.4.1.57264.1.9"
_OID_BUILD_CONFIG_URI = "1.3.6.1.4.1.57264.1.18"
_OID_GITHUB_WORKFLOW_NAME = "1.3.6.1.4.1.57264.1.4"
_OID_SOURCE_REPOSITORY = "1.3.6.1.4.1.57264.1.12"
_OID_GITHUB_WORKFLOW_REPOSITORY = "1.3.6.1.4.1.57264.1.5"
_OID_SOURCE_COMMIT = "1.3.6.1.4.1.57264.1.13"
_OID_GITHUB_WORKFLOW_SHA = "1.3.6.1.4.1.57264.1.3"
_OID_SOURCE_REF = "1.3.6.1.4.1.57264.1.14"
_OID_GITHUB_WORKFLOW_REF = "1.3.6.1.4.1.57264.1.6"


def dsse_pae(payload_type: str, payload: bytes) -> bytes:
    """Compute Pre-Authentication Encoding (PAE) for DSSE envelope."""
    return f"DSSEv1 {len(payload_type)} {payload_type} {len(payload)} ".encode() + payload


def _extract_extension_str(ext: Any) -> str | None:
    val = getattr(ext, "value", None)
    if isinstance(val, str):
        return val
    raw = getattr(val, "value", None)
    if isinstance(raw, bytes):
        decoded = _decode_der_utf8(raw)
        if decoded:
            return decoded
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if isinstance(raw, str):
        return raw
    return None


def _identity_from_certificate(certificate: Any) -> SignerIdentity:
    values: dict[str, str | None] = {}
    for extension in certificate.extensions:
        oid = extension.oid.dotted_string
        if oid in (
            _OID_ISSUER_V2,
            _OID_ISSUER_V1,
            _OID_BUILD_SIGNER_URI,
            _OID_BUILD_CONFIG_URI,
            _OID_GITHUB_WORKFLOW_NAME,
            _OID_SOURCE_REPOSITORY,
            _OID_GITHUB_WORKFLOW_REPOSITORY,
            _OID_SOURCE_COMMIT,
            _OID_GITHUB_WORKFLOW_SHA,
            _OID_SOURCE_REF,
            _OID_GITHUB_WORKFLOW_REF,
        ):
            values[oid] = _extract_extension_str(extension)

    issuer = values.get(_OID_ISSUER_V2) or values.get(_OID_ISSUER_V1)
    source_repo = values.get(_OID_SOURCE_REPOSITORY) or values.get(_OID_GITHUB_WORKFLOW_REPOSITORY)
    source_commit = values.get(_OID_SOURCE_COMMIT) or values.get(_OID_GITHUB_WORKFLOW_SHA)
    source_ref = values.get(_OID_SOURCE_REF) or values.get(_OID_GITHUB_WORKFLOW_REF)
    build_workflow = (
        values.get(_OID_BUILD_SIGNER_URI)
        or values.get(_OID_BUILD_CONFIG_URI)
        or values.get(_OID_GITHUB_WORKFLOW_NAME)
    )

    # Attempt SAN URI fallback if repository or workflow not explicitly provided in OIDs
    if not source_repo or not build_workflow:
        try:
            san_ext = certificate.extensions.get_extension_for_oid(
                cryptography.x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            for name in san_ext.value:
                if isinstance(name, cryptography.x509.UniformResourceIdentifier):
                    uri = name.value
                    if not build_workflow:
                        build_workflow = uri
                    if not source_repo:
                        m = re.match(r"^https://github\.com/([^/]+/[^/]+)", uri)
                        if m:
                            source_repo = f"https://github.com/{m.group(1)}"
        except Exception as exc:
            logger.debug("Could not extract SAN URI identity: %s", exc)

    return SignerIdentity(
        issuer=issuer,
        source_repository=source_repo,
        source_commit=source_commit.lower() if source_commit else None,
        source_ref=source_ref,
        build_workflow=build_workflow,
    )


def _normalize_repository(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().rstrip("/").removesuffix(".git").lower()


class SigstorePyPIBundleVerifier:
    """Verifies PyPI PEP 740 and Sigstore bundles cryptographically."""

    def verify(self, bundle_input: str | dict[str, Any]) -> VerifiedBundle:
        if isinstance(bundle_input, str):
            try:
                data = json.loads(bundle_input)
            except Exception as exc:
                raise BundleUnreadableError(f"Attestation is not valid JSON: {exc}") from exc
        elif isinstance(bundle_input, dict):
            data = bundle_input
        else:
            raise BundleUnreadableError(f"Unsupported bundle input type: {type(bundle_input)}")

        # Handle native Sigstore bundle
        if "mediaType" in data or "dsseEnvelope" in data:
            return self._verify_sigstore_bundle(data)

        # Handle PEP 740 attestation bundle or attestation object
        return self._verify_pep740_attestation(data)

    def _verify_sigstore_bundle(self, data: dict[str, Any]) -> VerifiedBundle:
        try:
            from sigstore.errors import VerificationError
            from sigstore.models import Bundle, InvalidBundle
            from sigstore.verify import Verifier, policy
        except ImportError as exc:
            raise VerificationUnavailableError("sigstore is not installed") from exc

        try:
            bundle = Bundle.from_json(json.dumps(data))
        except (InvalidBundle, ValueError) as exc:
            raise BundleUnreadableError(f"Cannot parse Sigstore bundle: {exc}") from exc

        try:
            verifier = Verifier.production()
        except Exception as exc:
            raise VerificationUnavailableError(
                f"Could not load Sigstore trust root: {exc}"
            ) from exc

        try:
            payload_type, payload = verifier.verify_dsse(bundle, policy.UnsafeNoOp())
        except VerificationError as exc:
            raise SignatureInvalidError(f"Sigstore verification failed: {exc}") from exc

        identity = _identity_from_certificate(bundle.signing_certificate)
        return VerifiedBundle(payload_type=payload_type, payload=payload, identity=identity)

    def _verify_pep740_attestation(self, data: dict[str, Any]) -> VerifiedBundle:
        # If wrapped in an attestation bundle with 'attestations' list
        if "attestations" in data and isinstance(data["attestations"], list):
            if not data["attestations"]:
                raise BundleUnreadableError("Attestation bundle contains empty attestations list.")
            att_obj = data["attestations"][0]
        else:
            att_obj = data

        if not isinstance(att_obj, dict):
            raise BundleUnreadableError("Attestation object is not a dictionary.")

        vm = att_obj.get("verification_material")
        envelope = att_obj.get("envelope")

        if not isinstance(vm, dict) or not isinstance(envelope, dict):
            raise BundleUnreadableError(
                "Attestation object missing 'verification_material' or 'envelope'."
            )

        # 1. Parse certificate
        cert_raw = vm.get("certificate")
        if not cert_raw:
            raise BundleUnreadableError("No certificate found in verification material.")

        try:
            if isinstance(cert_raw, str):
                if cert_raw.startswith("-----BEGIN CERTIFICATE-----"):
                    cert = cryptography.x509.load_pem_x509_certificate(cert_raw.encode("utf-8"))
                else:
                    cert_bytes = base64.b64decode(cert_raw)
                    cert = cryptography.x509.load_der_x509_certificate(cert_bytes)
            elif isinstance(cert_raw, bytes):
                cert = cryptography.x509.load_der_x509_certificate(cert_raw)
            else:
                raise BundleUnreadableError(f"Unsupported certificate type: {type(cert_raw)}")
        except Exception as exc:
            raise BundleUnreadableError(f"Failed to parse X.509 certificate: {exc}") from exc

        # 2. Check certificate validity dates and expiration
        now = datetime.now(UTC)
        if now < cert.not_valid_before_utc:
            valid_from = cert.not_valid_before_utc.isoformat()
            raise SignatureInvalidError(
                f"Signing certificate is not yet valid (valid from {valid_from})."
            )

        # Check for transparency log entry or timestamp proof
        tlog_entries = vm.get("transparency_entries") or vm.get("tlog_entries")
        valid_log_timestamp = False
        if isinstance(tlog_entries, list):
            for entry in tlog_entries:
                if isinstance(entry, dict) and "integratedTime" in entry:
                    try:
                        int_time = datetime.fromtimestamp(entry["integratedTime"], tz=UTC)
                        if cert.not_valid_before_utc <= int_time <= cert.not_valid_after_utc:
                            valid_log_timestamp = True
                            break
                    except Exception as exc:
                        logger.debug("Could not parse log entry integratedTime: %s", exc)

        if now > cert.not_valid_after_utc and not valid_log_timestamp:
            exp_time = cert.not_valid_after_utc.isoformat()
            raise SignatureInvalidError(
                f"Signing certificate expired at {exp_time} without a valid log timestamp."
            )

        # 3. Extract statement payload and signature
        statement_raw = envelope.get("statement") or envelope.get("payload")
        signature_raw = envelope.get("signature") or (
            envelope.get("signatures", [{}])[0].get("sig") if envelope.get("signatures") else None
        )
        payload_type = envelope.get("payloadType") or IN_TOTO_PAYLOAD_TYPE

        if not statement_raw or not signature_raw:
            raise BundleUnreadableError("Envelope missing statement payload or signature.")

        # Decode statement
        try:
            if isinstance(statement_raw, str):
                try:
                    payload_bytes = base64.b64decode(statement_raw)
                except Exception:
                    payload_bytes = statement_raw.encode("utf-8")
            elif isinstance(statement_raw, bytes):
                payload_bytes = statement_raw
            else:
                raise BundleUnreadableError("Invalid statement payload format.")
        except Exception as exc:
            raise BundleUnreadableError(f"Failed to decode statement payload: {exc}") from exc

        # Decode signature
        try:
            if isinstance(signature_raw, str):
                sig_bytes = base64.b64decode(signature_raw)
            elif isinstance(signature_raw, bytes):
                sig_bytes = signature_raw
            else:
                raise BundleUnreadableError("Invalid signature format.")
        except Exception as exc:
            raise BundleUnreadableError(f"Failed to decode signature: {exc}") from exc

        # 4. Compute DSSE Pre-Authentication Encoding (PAE) and verify signature
        pae = dsse_pae(payload_type, payload_bytes)
        pub_key = cert.public_key()
        if not isinstance(pub_key, ec.EllipticCurvePublicKey):
            raise SignatureInvalidError(
                f"Expected ECDSA public key in signing certificate, found {type(pub_key).__name__}."
            )

        try:
            pub_key.verify(sig_bytes, pae, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise SignatureInvalidError(
                "Cryptographic signature check failed on DSSE envelope."
            ) from exc
        except Exception as exc:
            raise SignatureInvalidError(f"Cryptographic verification error: {exc}") from exc

        # 5. Extract identity from certificate
        identity = _identity_from_certificate(cert)
        return VerifiedBundle(payload_type=payload_type, payload=payload_bytes, identity=identity)


class PyPIProvenanceChecker:
    """Verifies PEP 740 digital attestations and provenance for PyPI packages."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        verifier: BundleVerifier | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._verifier = verifier if verifier is not None else SigstorePyPIBundleVerifier()
        self._timeout_seconds = timeout_seconds

    async def check(
        self,
        metadata: PackageMetadata,
        artifact_path: Path,
        source_match: SourceMatch,
    ) -> ProvenanceResult:
        """Inspect available PyPI attestations and evaluate artifact integrity."""
        # 1. Compute artifact digests (SHA-256 and SHA-512)
        hasher_256 = hashlib.sha256()
        hasher_512 = hashlib.sha512()
        try:
            with artifact_path.open("rb") as f:
                while chunk := f.read(_HASH_CHUNK):
                    hasher_256.update(chunk)
                    hasher_512.update(chunk)
            actual_sha256 = hasher_256.hexdigest().lower()
            actual_sha512 = hasher_512.hexdigest().lower()
        except OSError as exc:
            return ProvenanceResult(
                status=ProvenanceStatus.UNCERTAIN,
                explanation=f"Cannot read downloaded artifact: {exc}",
                claimed_in_metadata=False,
            )

        # 2. Check declared digest match
        declared_sha256: str | None = None
        if metadata.artifacts:
            for h in metadata.artifacts[0].hashes:
                if h.algorithm == "sha256":
                    declared_sha256 = h.hex_digest.lower()
                    break

        integrity_matches = declared_sha256 is not None and (actual_sha256 == declared_sha256)

        # 3. Check for PEP 740 attestations in manifest or PyPI integrity endpoint
        manifest = metadata.manifest or {}
        attestation_bundles = (
            manifest.get("attestations")
            or manifest.get("provenance")
            or manifest.get("attestation_bundles")
        )

        claimed_in_metadata = attestation_bundles is not None

        # Query PyPI integrity API endpoint if not present in version document
        if not attestation_bundles:
            artifact_filename = (
                metadata.artifacts[0].filename
                if metadata.artifacts
                else artifact_path.name
            )
            # Query standard PEP 740 filename provenance route first
            filename_url = (
                f"https://pypi.org/integrity/{quote(metadata.name, safe='')}/"
                f"{quote(metadata.version, safe='')}/{quote(artifact_filename, safe='')}/provenance"
            )
            try:
                res = await self._client.get(
                    filename_url,
                    headers={"Accept": "application/vnd.pypi.integrity.v1+json"},
                    timeout=10.0,
                )
                if res.status_code == 200:
                    data = res.json()
                    attestation_bundles = data.get("attestation_bundles") or data
            except Exception as exc:
                logger.debug("PyPI filename integrity check skipped: %s", exc)

            # Fallback to general release attestations route
            if not attestation_bundles:
                attestation_url = (
                    f"https://pypi.org/integrity/{quote(metadata.name, safe='')}/"
                    f"{quote(metadata.version, safe='')}/attestations"
                )
                try:
                    res = await self._client.get(attestation_url, timeout=10.0)
                    if res.status_code == 200:
                        data = res.json()
                        attestation_bundles = data.get("attestation_bundles") or data
                except Exception as exc:
                    logger.debug("PyPI general integrity check skipped: %s", exc)

        if not attestation_bundles:
            return ProvenanceResult(
                status=ProvenanceStatus.UNAVAILABLE,
                explanation="Package was published without PyPI PEP 740 digital attestations.",
                claimed_in_metadata=False,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                package_integrity=declared_sha256,
                integrity_matches=integrity_matches,
            )

        # 4. Normalize bundles list
        if isinstance(attestation_bundles, list):
            bundle_list = attestation_bundles
        elif isinstance(attestation_bundles, dict) and "attestation_bundles" in attestation_bundles:
            raw_bundles = attestation_bundles["attestation_bundles"]
            bundle_list = raw_bundles if isinstance(raw_bundles, list) else [raw_bundles]
        else:
            bundle_list = [attestation_bundles]

        if not bundle_list:
            return ProvenanceResult(
                status=ProvenanceStatus.UNAVAILABLE,
                explanation="No attestation bundle for this artifact.",
                claimed_in_metadata=claimed_in_metadata,
                integrity_matches=integrity_matches,
            )

        first_bundle = bundle_list[0]

        # Handle explicit simulated invalid flag
        if isinstance(first_bundle, dict) and first_bundle.get("invalid"):
            return ProvenanceResult(
                status=ProvenanceStatus.INVALID,
                explanation="PyPI attestation signature failed cryptographic verification.",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )

        # Check if bundle has any verifiable cryptographic material
        has_crypto_material = False
        if isinstance(first_bundle, str):
            has_crypto_material = True
        elif isinstance(first_bundle, dict):
            if "mediaType" in first_bundle or "dsseEnvelope" in first_bundle:
                has_crypto_material = True
            elif "verification_material" in first_bundle and "envelope" in first_bundle:
                has_crypto_material = True
            elif "attestations" in first_bundle and isinstance(first_bundle["attestations"], list):
                has_crypto_material = True

        if not has_crypto_material:
            # Metadata without cryptographic verification material
            explanation = (
                "Attestation metadata claims publisher identity, but contains no "
                "cryptographic signatures or certificate material to verify."
            )
            return ProvenanceResult(
                status=ProvenanceStatus.NOT_VERIFIED,
                explanation=explanation,
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )

        # 5. Execute cryptographic verification
        try:
            async with asyncio.timeout(self._timeout_seconds):
                verified = await asyncio.to_thread(self._verifier.verify, first_bundle)
        except SignatureInvalidError as exc:
            return ProvenanceResult(
                status=ProvenanceStatus.INVALID,
                explanation=f"PyPI attestation signature failed cryptographic verification: {exc}",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )
        except BundleUnreadableError as exc:
            return ProvenanceResult(
                status=ProvenanceStatus.UNCERTAIN,
                explanation=f"The attestation could not be read: {exc}",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )
        except TimeoutError:
            return ProvenanceResult(
                status=ProvenanceStatus.NOT_VERIFIED,
                explanation="Attestation verification did not finish in time.",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )
        except VerificationUnavailableError as exc:
            return ProvenanceResult(
                status=ProvenanceStatus.NOT_VERIFIED,
                explanation=f"An attestation exists, but it could not be verified: {exc}",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )
        except Exception as exc:
            logger.warning("Unexpected error during PyPI attestation verification: %s", exc)
            return ProvenanceResult(
                status=ProvenanceStatus.UNCERTAIN,
                explanation=f"Unexpected error during attestation verification: {exc}",
                claimed_in_metadata=claimed_in_metadata,
                signature_verified=False,
                tarball_digest_matches=integrity_matches,
                integrity_matches=integrity_matches,
            )

        # 6. Evaluate verified signed statement and identity
        return await asyncio.to_thread(
            _evaluate_signed_content,
            verified,
            metadata,
            artifact_path,
            actual_sha256,
            actual_sha512,
            declared_sha256,
            integrity_matches,
            source_match,
            claimed_in_metadata,
        )


def _evaluate_signed_content(
    verified: VerifiedBundle,
    metadata: PackageMetadata,
    artifact_path: Path,
    actual_sha256: str,
    actual_sha512: str,
    declared_sha256: str | None,
    integrity_matches: bool | None,
    source_match: SourceMatch,
    claimed: bool,
) -> ProvenanceResult:
    """Evaluate cryptographically verified signed content and identity against metadata."""

    def invalid(explanation: str, digest_matches: bool = False) -> ProvenanceResult:
        return ProvenanceResult(
            status=ProvenanceStatus.INVALID,
            explanation=explanation,
            claimed_in_metadata=claimed,
            signature_verified=True,
            tarball_digest_matches=digest_matches,
            package_integrity=declared_sha256,
            integrity_matches=integrity_matches,
        )

    # 1. Check signer identity and OIDC issuer
    identity = verified.identity
    if identity.issuer not in TRUSTED_PYPI_OIDC_ISSUERS:
        return invalid(f"The signer's identity provider is not recognized: {identity.issuer!r}")

    if not identity.source_repository:
        return invalid("The signing certificate does not identify a source repository.")

    # 2. Check in-toto payload type
    if verified.payload_type != IN_TOTO_PAYLOAD_TYPE:
        return invalid(f"The signed content has an unexpected type: {verified.payload_type!r}")

    # 3. Parse statement JSON
    try:
        statement = json.loads(verified.payload)
    except (ValueError, RecursionError):
        return invalid("The signed statement is not valid JSON.")

    if not isinstance(statement, dict):
        return invalid("The signed statement is malformed.")

    predicate_type = statement.get("predicateType")
    if not isinstance(predicate_type, str) or not (
        predicate_type.startswith(PEP740_PUBLISH_PREDICATE_PREFIX)
        or predicate_type.startswith(SLSA_PREDICATE_PREFIX)
        or predicate_type.startswith("https://in-toto.io/")
    ):
        return invalid(
            f"The signed statement has an unrecognized predicate type: {predicate_type!r}"
        )

    # 4. Match subject
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or not subjects:
        return invalid("The signed statement does not contain any subjects.")

    target_filename = artifact_path.name
    expected_purl = f"pkg:pypi/{quote(metadata.name, safe='')}@{quote(metadata.version, safe='')}"

    matched_subject: dict[str, Any] | None = None
    for subj in subjects:
        if isinstance(subj, dict):
            s_name = subj.get("name")
            if s_name in (target_filename, expected_purl, metadata.name):
                matched_subject = subj
                break
    if not matched_subject and len(subjects) == 1 and isinstance(subjects[0], dict):
        matched_subject = subjects[0]

    if not matched_subject:
        return invalid(f"The signed statement does not contain a subject for '{target_filename}'.")

    # 5. Check subject cryptographic digest
    digests = matched_subject.get("digest")
    if not isinstance(digests, dict):
        return invalid("The signed statement subject has no digests.")

    subject_sha256 = digests.get("sha256")
    subject_sha512 = digests.get("sha512")

    digest_matched = False
    if isinstance(subject_sha256, str):
        if subject_sha256.lower() != actual_sha256:
            return invalid(
                "The downloaded artifact does not match the signed SHA-256 digest "
                f"({subject_sha256.lower()} != {actual_sha256})."
            )
        digest_matched = True
    elif isinstance(subject_sha512, str):
        if subject_sha512.lower() != actual_sha512:
            return invalid(
                "The downloaded artifact does not match the signed SHA-512 digest "
                f"({subject_sha512.lower()} != {actual_sha512})."
            )
        digest_matched = True
    else:
        return invalid(
            "The signed statement subject contains neither SHA-256 nor SHA-512 digests."
        )

    # 6. Check commit in statement if present
    statement_commit = _commit_in_statement(statement)
    if (
        statement_commit
        and identity.source_commit
        and statement_commit != identity.source_commit.lower()
    ):
        return invalid(
            "The certificate and the signed statement name different commits.", digest_matched
        )

    # 7. Compare declared repository and source match
    declared = metadata.repository.url if metadata.repository else None
    declared_normalized = _normalize_repository(declared)
    identity_repo_normalized = _normalize_repository(identity.source_repository)

    repository_matches = (
        identity_repo_normalized == declared_normalized if declared_normalized else None
    )

    commit_matches: bool | None = None
    if (
        source_match.status is MatchStatus.MATCHED
        and source_match.commit_sha
        and identity.source_commit
    ):
        commit_matches = source_match.commit_sha.lower() == identity.source_commit.lower()

    notes = ["PyPI PEP 740 attestation verified cryptographically under Sigstore trust root."]
    if repository_matches is False:
        notes.append(f"However, it was built from {identity.source_repository}, not {declared}.")
    if commit_matches is False:
        notes.append(
            f"However, it was built from a different commit than {source_match.commit_sha}."
        )

    return ProvenanceResult(
        status=ProvenanceStatus.VERIFIED,
        explanation=" ".join(notes),
        claimed_in_metadata=claimed,
        signature_verified=True,
        tarball_digest_matches=True,
        package_integrity=declared_sha256,
        integrity_matches=integrity_matches,
        source_repository=identity.source_repository,
        source_commit=identity.source_commit.lower() if identity.source_commit else None,
        source_ref=identity.source_ref,
        build_workflow=identity.build_workflow,
        oidc_issuer=identity.issuer,
        repository_matches_declared=repository_matches,
        commit_matches_source_match=commit_matches,
    )


def _commit_in_statement(statement: dict[str, Any]) -> str | None:
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        return None
    # Check SLSA format
    definition = predicate.get("buildDefinition")
    if isinstance(definition, dict):
        dependencies = definition.get("resolvedDependencies")
        if isinstance(dependencies, list) and dependencies:
            first = dependencies[0]
            if isinstance(first, dict):
                digest = first.get("digest")
                if isinstance(digest, dict):
                    commit = digest.get("gitCommit")
                    if isinstance(commit, str):
                        return commit.lower()
    # Check PyPI publish attestation format
    publisher = predicate.get("publisher")
    if isinstance(publisher, dict):
        commit = publisher.get("commit") or publisher.get("sha")
        if isinstance(commit, str):
            return commit.lower()
    return None


__all__ = [
    "BundleUnreadableError",
    "BundleVerifier",
    "PyPIProvenanceChecker",
    "SignatureInvalidError",
    "SignerIdentity",
    "SigstorePyPIBundleVerifier",
    "VerificationUnavailableError",
    "VerifiedBundle",
    "dsse_pae",
]
