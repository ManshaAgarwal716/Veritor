"""End-to-end tests for PyPI scan pipeline and scan manager."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
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
from app.provenance.pypi import PyPIProvenanceChecker
from app.scans.manager import ScanManager
from app.scans.pipeline import execute_scan_pipeline
from app.schemas.scans import Ecosystem, ScanRequest, ScanStage, ScanState
from app.source.models import (
    Confidence,
    GitHubRepository,
    MatchMethod,
    MatchStatus,
    SourceMatch,
)
from tests.test_release_analysis import FakeResolver

pytestmark = pytest.mark.anyio


def make_wheel(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode())
    return buffer.getvalue()


class FakePyPIAdapter(PackageAdapter):
    ecosystem = Ecosystem.PYPI

    def __init__(self, metadata: PackageMetadata, files: dict[str, str]) -> None:
        self.data = make_wheel(files)
        digest = hashlib.sha256(self.data).hexdigest()
        self.metadata = metadata.model_copy(
            update={
                "artifacts": (
                    ArtifactInfo(
                        filename="requests-2.31.0-py3-none-any.whl",
                        url="https://files.pythonhosted.org/packages/wheel/requests-2.31.0.whl",
                        hashes=(ArtifactHash(algorithm="sha256", hex_digest=digest),),
                    ),
                )
            }
        )

    async def fetch_metadata(self, name: str, version: str) -> PackageMetadata:
        return self.metadata

    async def download_artifact(
        self, artifact: ArtifactInfo, destination: Path
    ) -> DownloadedArtifact:
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / artifact.filename
        path.write_bytes(self.data)
        return DownloadedArtifact(
            path=path,
            size_bytes=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(),
            verified_algorithms=("sha256",),
        )


async def test_pypi_pipeline_execution(tmp_path: Path):
    work_dir = tmp_path / "work"
    scan_id = uuid4()
    files = {
        "requests/__init__.py": "# requests init\n__version__ = '2.31.0'\n",
        "requests/api.py": "def get(url):\n    return url\n",
        "requests-2.31.0.dist-info/METADATA": (
            "Metadata-Version: 2.1\nName: requests\nVersion: 2.31.0\n"
        ),
    }

    meta = PackageMetadata(
        ecosystem=Ecosystem.PYPI,
        name="requests",
        version="2.31.0",
        description="Python HTTP for Humans",
        license="Apache 2.0",
        homepage="https://requests.readthedocs.io",
        repository=SourceRepository(
            declared="https://github.com/psf/requests",
            url="https://github.com/psf/requests",
        ),
        source_commit=None,
        published_at=datetime.now(UTC),
        dependencies=(),
        scripts={},
        has_install_script=False,
        entry_points={},
        artifacts=(),
        manifest={},
    )

    adapter = FakePyPIAdapter(meta, files)

    # Matched source match
    match = SourceMatch(
        status=MatchStatus.MATCHED,
        confidence=Confidence.HIGH,
        method=MatchMethod.PACKAGE_TAG,
        explanation="Matched tag v2.31.0",
        repository=GitHubRepository(owner="psf", name="requests"),
        commit_sha="a" * 40,
    )
    resolver = FakeResolver(match, files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = PyPIProvenanceChecker(client)
        mock_ollama = AsyncMock(spec=OllamaClient)
        mock_ollama.model = "qwen2.5-coder:7b"
        investigator = AIInvestigator(client=mock_ollama)

        progress_events: list[tuple[ScanStage, int, str]] = []

        async def track_progress(stage: ScanStage, percent: int, msg: str) -> None:
            progress_events.append((stage, percent, msg))

        report = await execute_scan_pipeline(
            scan_id=scan_id,
            ecosystem=Ecosystem.PYPI,
            package_name="requests",
            version="2.31.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
            on_progress=track_progress,
            clean_artifacts_on_exit=True,
        )

        assert report.scan_id == scan_id
        assert report.status is ScanState.COMPLETED
        assert report.ecosystem is Ecosystem.PYPI
        assert report.package_name == "requests"
        assert report.version == "2.31.0"
        assert report.comparison is not None
        assert report.risk is not None
        assert report.provenance is not None
        assert report.ai is not None


async def test_scan_manager_pypi_request(tmp_path: Path):
    manager = ScanManager(base_work_dir=tmp_path / "scans")

    req = ScanRequest(
        ecosystem=Ecosystem.PYPI,
        package_name="sample-package",
        version="1.0.0",
    )

    resp = await manager.create_scan(req)
    assert resp.ecosystem is Ecosystem.PYPI
    assert resp.package_name == "sample-package"
    assert resp.version == "1.0.0"
    assert resp.status == ScanState.ACCEPTED

    # Get scan status
    status = manager.get_scan(resp.scan_id)
    assert status is not None
    assert status.scan_id == resp.scan_id
    assert status.ecosystem is Ecosystem.PYPI
