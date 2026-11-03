"""Concurrency, bounded resource usage, and stress integration tests.

Addresses audit finding TST-02:
- Multiple simultaneous scans
- Duplicate scan requests
- Shared temporary directory isolation
- Concurrent archive extraction
- Database session isolation
- Scheduler overlap prevention & bounded concurrency
- Cancellation and failure cleanup
- Ollama timeout handling
- External API rate-limit behavior
"""

import asyncio
import hashlib
import io
import tarfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.base import (
    ArtifactInfo,
    DownloadedArtifact,
    PackageAdapter,
    PackageMetadata,
)
from app.ai.client import OllamaClient
from app.ai.investigator import AIInvestigator
from app.ai.models import AIInvestigationStatus
from app.archives.extract import ExtractionLimits, extract_archive
from app.db import Base
from app.db.repository import ScanRepository
from app.monitoring.scheduler import DEFAULT_MAX_CONCURRENCY, ReleaseMonitoringScheduler
from app.provenance.npm import NpmProvenanceChecker
from app.scans.manager import ScanManager
from app.scans.pipeline import execute_scan_pipeline
from app.schemas.scans import Ecosystem, ScanRequest, ScanStage, ScanState
from app.source.models import SourceArchive, SourceMatch
from tests.test_comparison import make_metadata, manifest, matched
from tests.test_provenance import FakeVerifier

pytestmark = pytest.mark.anyio


def create_tarball(files: dict[str, str]) -> bytes:
    """Helper to create an in-memory tarball."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(data)
            info.mtime = int(datetime.now(UTC).timestamp())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_mock_ollama() -> AsyncMock:
    """Creates a mock Ollama client with expected attributes."""
    mock = AsyncMock(spec=OllamaClient)
    mock.model = "qwen2.5-coder:7b"
    mock.chat_json.return_value = {
        "summary": "AI investigation completed successfully.",
        "findings_explanations": [],
        "overall_uncertainty": "Low",
        "recommendations": [],
    }
    return mock


class ConcurrencyFakeAdapter(PackageAdapter):
    """Adapter supporting configurable delay and file payloads."""

    def __init__(
        self,
        metadata: PackageMetadata,
        files: dict[str, str],
        delay_seconds: float = 0.0,
        fail_download: bool = False,
        rate_limit: bool = False,
    ) -> None:
        self.metadata = metadata.model_copy(
            update={
                "artifacts": (
                    ArtifactInfo.model_construct(
                        filename="package.tgz",
                        url="https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                        hashes=(),
                        size_bytes=None,
                    ),
                )
            }
        )
        self.files = files
        self.data = create_tarball(files)
        self.delay_seconds = delay_seconds
        self.fail_download = fail_download
        self.rate_limit = rate_limit

    async def fetch_metadata(self, name: str, version: str) -> PackageMetadata:
        if self.rate_limit:
            req = httpx.Request("GET", f"https://registry.npmjs.org/{name}")
            resp = httpx.Response(429, request=req, text="Too Many Requests")
            raise httpx.HTTPStatusError("Rate limit exceeded (429)", request=req, response=resp)
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        return self.metadata.model_copy(update={"name": name, "version": version})

    async def download_artifact(
        self, artifact: ArtifactInfo, destination: Path
    ) -> DownloadedArtifact:
        if self.fail_download:
            raise OSError("Simulated network/disk failure during artifact download")
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "package.tgz"
        path.write_bytes(self.data)
        return DownloadedArtifact.model_construct(
            path=path,
            size_bytes=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(),
            verified_algorithms=(),
        )


class ConcurrencyFakeResolver:
    """Resolver supporting configurable source files and delay."""

    def __init__(
        self, match: SourceMatch, files: dict[str, str], delay_seconds: float = 0.0
    ) -> None:
        self._match = match
        self.files = files
        self.delay_seconds = delay_seconds

    async def resolve(self, metadata: PackageMetadata) -> SourceMatch:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        return self._match

    async def download_source(self, match: SourceMatch, destination: Path) -> SourceArchive:
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "source.tar.gz"
        source_data = create_tarball(self.files)
        path.write_bytes(source_data)
        return SourceArchive.model_construct(
            path=path,
            commit_sha=match.commit_sha or "HEAD",
        )


@pytest.fixture
def in_memory_session_factory() -> Iterator[sessionmaker[Session]]:
    """Creates an isolated in-memory SQLite sessionmaker with shared connection pool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)


async def test_concurrent_multiple_simultaneous_scans(tmp_path: Path) -> None:
    """Verify simultaneous scans execute and complete concurrently without interference."""
    num_scans = 5
    base_dir = tmp_path / "concurrent_scans"

    def make_adapter() -> ConcurrencyFakeAdapter:
        files = {
            "package.json": manifest(name="dynamic-pkg", version="1.0.0"),
            "index.js": "console.log('dynamic-pkg');",
        }
        return ConcurrencyFakeAdapter(make_metadata(name="dynamic-pkg"), files, delay_seconds=0.01)

    manager = ScanManager(
        base_work_dir=base_dir,
        adapter_factory=lambda client: make_adapter(),
        resolver_factory=lambda client: ConcurrencyFakeResolver(
            matched(), {"package.json": manifest(name="dynamic-pkg", version="1.0.0")}
        ),
        checker_factory=lambda client: NpmProvenanceChecker(client, verifier=FakeVerifier()),
        ai_investigator_factory=lambda: AIInvestigator(client=make_mock_ollama()),
    )

    requests = [
        ScanRequest(ecosystem=Ecosystem.NPM, package_name=f"pkg-{i}", version="1.0.0")
        for i in range(num_scans)
    ]

    records = await asyncio.gather(*[manager.create_scan(req) for req in requests])
    assert len(records) == num_scans
    assert len({r.scan_id for r in records}) == num_scans

    # Wait for all background tasks to finish
    await asyncio.gather(*manager._active_tasks.values())

    # Verify all completed successfully
    for record in records:
        scan = manager.get_scan(record.scan_id)
        assert scan is not None
        assert scan.status == ScanState.COMPLETED
        assert scan.stage == ScanStage.COMPLETED
        assert scan.progress_percent == 100
        assert scan.report is not None
        assert scan.report.scan_id == record.scan_id


async def test_concurrent_duplicate_scan_requests(tmp_path: Path) -> None:
    """Verify concurrent duplicate requests receive unique scan IDs without state corruption."""
    base_dir = tmp_path / "dup_scans"
    files = {
        "package.json": manifest(name="shared-lib", version="2.0.0"),
        "index.js": "module.exports = 42;",
    }

    manager = ScanManager(
        base_work_dir=base_dir,
        adapter_factory=lambda _: ConcurrencyFakeAdapter(
            make_metadata(name="shared-lib"), files, delay_seconds=0.01
        ),
        resolver_factory=lambda _: ConcurrencyFakeResolver(matched(), files),
        checker_factory=lambda client: NpmProvenanceChecker(client, verifier=FakeVerifier()),
        ai_investigator_factory=lambda: AIInvestigator(client=make_mock_ollama()),
    )

    req = ScanRequest(ecosystem=Ecosystem.NPM, package_name="shared-lib", version="2.0.0")
    num_duplicates = 4

    records = await asyncio.gather(*[manager.create_scan(req) for _ in range(num_duplicates)])

    # All must have unique IDs
    ids = [r.scan_id for r in records]
    assert len(set(ids)) == num_duplicates

    await asyncio.gather(*manager._active_tasks.values())

    for scan_id in ids:
        scan = manager.get_scan(scan_id)
        assert scan is not None
        assert scan.status == ScanState.COMPLETED
        assert scan.report is not None
        assert scan.report.package_name == "shared-lib"
        assert scan.report.version == "2.0.0"


async def test_shared_temporary_directory_isolation(tmp_path: Path) -> None:
    """Verify concurrent scans operate in isolated work directories without cross-contamination."""
    base_dir = tmp_path / "isolated_scans"

    scan_a_files = {
        "package.json": manifest(name="pkg-a", version="1.0.0"),
        "secret.txt": "token-for-pkg-a",
    }
    scan_b_files = {
        "package.json": manifest(name="pkg-b", version="1.0.0"),
        "secret.txt": "token-for-pkg-b",
    }

    scan_a_id = uuid4()
    scan_b_id = uuid4()

    dir_a = base_dir / str(scan_a_id)
    dir_b = base_dir / str(scan_b_id)

    adapter_a = ConcurrencyFakeAdapter(
        make_metadata(name="pkg-a"), scan_a_files, delay_seconds=0.02
    )
    adapter_b = ConcurrencyFakeAdapter(
        make_metadata(name="pkg-b"), scan_b_files, delay_seconds=0.02
    )

    resolver_a = ConcurrencyFakeResolver(matched(), scan_a_files)
    resolver_b = ConcurrencyFakeResolver(matched(), scan_b_files)

    mock_ollama = make_mock_ollama()

    # Execute pipelines with clean_artifacts_on_exit=False to inspect directory states
    async def run_pipeline(
        sid: UUID, pkg_name: str, work_dir: Path, adapter: Any, resolver: Any
    ) -> Any:
        transport = httpx.MockTransport(lambda _: httpx.Response(404))
        async with httpx.AsyncClient(transport=transport) as client:
            checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
            return await execute_scan_pipeline(
                scan_id=sid,
                ecosystem=Ecosystem.NPM,
                package_name=pkg_name,
                version="1.0.0",
                work_dir=work_dir,
                adapter=adapter,
                resolver=resolver,  # type: ignore[arg-type]
                provenance_checker=checker,
                ai_investigator=AIInvestigator(client=mock_ollama),
                clean_artifacts_on_exit=False,
            )

    report_a, report_b = await asyncio.gather(
        run_pipeline(scan_a_id, "pkg-a", dir_a, adapter_a, resolver_a),
        run_pipeline(scan_b_id, "pkg-b", dir_b, adapter_b, resolver_b),
    )

    assert report_a.package_name == "pkg-a"
    assert report_b.package_name == "pkg-b"

    # Verify directory contents were completely isolated
    extracted_a = dir_a / "package" / "secret.txt"
    extracted_b = dir_b / "package" / "secret.txt"

    assert extracted_a.exists()
    assert extracted_b.exists()
    assert extracted_a.read_text(encoding="utf-8") == "token-for-pkg-a"
    assert extracted_b.read_text(encoding="utf-8") == "token-for-pkg-b"


async def test_concurrent_archive_extraction(tmp_path: Path) -> None:
    """Verify thread safety during concurrent archive extractions into separate directories."""
    archives_dir = tmp_path / "archives"
    dest_base = tmp_path / "dest"
    archives_dir.mkdir(parents=True)
    dest_base.mkdir(parents=True)

    num_archives = 8
    archive_paths: list[Path] = []
    dest_paths: list[Path] = []

    for i in range(num_archives):
        files = {f"file_{i}_{j}.txt": f"Content of file {j} in archive {i}" for j in range(5)}
        tar_bytes = create_tarball(files)
        arc_path = archives_dir / f"archive_{i}.tar.gz"
        arc_path.write_bytes(tar_bytes)
        archive_paths.append(arc_path)
        dest_paths.append(dest_base / f"dest_{i}")

    # Extract all 8 archives concurrently
    limits = ExtractionLimits()
    inventories = await asyncio.gather(
        *[
            asyncio.to_thread(extract_archive, arc, dest, limits)
            for arc, dest in zip(archive_paths, dest_paths, strict=True)
        ]
    )

    assert len(inventories) == num_archives
    for i, inv in enumerate(inventories):
        assert len(inv.entries) == 5
        for j in range(5):
            expected_rel = f"file_{i}_{j}.txt"
            assert any(e.path == expected_rel for e in inv.entries)


async def test_database_session_isolation_under_concurrency(
    tmp_path: Path, in_memory_session_factory: sessionmaker[Session]
) -> None:
    """Verify concurrent scan persistence across separate DB sessions without lock errors."""
    base_dir = tmp_path / "db_concurrency"
    num_scans = 5

    def get_adapter() -> ConcurrencyFakeAdapter:
        files = {
            "package.json": manifest(name="db-pkg", version="1.0.0"),
            "index.js": "console.log('db-pkg');",
        }
        return ConcurrencyFakeAdapter(make_metadata(name="db-pkg"), files, delay_seconds=0.01)

    manager = ScanManager(
        base_work_dir=base_dir,
        session_factory=in_memory_session_factory,
        adapter_factory=lambda _: get_adapter(),
        resolver_factory=lambda _: ConcurrencyFakeResolver(
            matched(), {"package.json": manifest(name="db-pkg", version="1.0.0")}
        ),
        checker_factory=lambda client: NpmProvenanceChecker(client, verifier=FakeVerifier()),
        ai_investigator_factory=lambda: AIInvestigator(client=make_mock_ollama()),
    )

    requests = [
        ScanRequest(ecosystem=Ecosystem.NPM, package_name=f"db-pkg-{i}", version="1.0.0")
        for i in range(num_scans)
    ]

    records = await asyncio.gather(*[manager.create_scan(req) for req in requests])
    await asyncio.gather(*manager._active_tasks.values())

    # Read all back from a fresh independent DB session
    with in_memory_session_factory() as session:
        repo = ScanRepository(session)
        for r in records:
            db_scan = repo.get_scan(r.scan_id)
            assert db_scan is not None
            assert db_scan.status == ScanState.COMPLETED.value
            assert db_scan.progress_percent == 100

            db_report = repo.get_report(r.scan_id)
            assert db_report is not None
            assert db_report.scan_id == r.scan_id


async def test_scheduler_overlap_prevention(tmp_path: Path) -> None:
    """Verify that concurrent calls to check_watchlist_now are guarded by _check_lock."""
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    manager.add_watchlist_entry("npm", "express", "Web framework")

    scheduler = ReleaseMonitoringScheduler(request_delay_seconds=0.0)

    # Acquire the lock to simulate an active in-flight check
    await scheduler._check_lock.acquire()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"dist-tags": {"latest": "4.19.2"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await scheduler.check_watchlist_now(
            session=None,
            scan_manager=manager,
            client=client,
        )
        # When locked, check_watchlist_now returns early with 0 checked
        assert res.checked_count == 0
        assert res.updates_detected == 0

    scheduler._check_lock.release()


async def test_scheduler_bounded_concurrency_semaphore(tmp_path: Path) -> None:
    """Verify watchlist checks use bounded concurrency matching DEFAULT_MAX_CONCURRENCY."""
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    for i in range(8):
        manager.add_watchlist_entry("npm", f"pkg-{i}", "Monitored library")

    scheduler = ReleaseMonitoringScheduler(
        request_delay_seconds=0.0, max_concurrency=DEFAULT_MAX_CONCURRENCY
    )

    max_active = 0
    current_active = 0
    lock = asyncio.Lock()

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal max_active, current_active
        async with lock:
            current_active += 1
            if current_active > max_active:
                max_active = current_active
        await asyncio.sleep(0.02)
        async with lock:
            current_active -= 1
        return httpx.Response(200, json={"dist-tags": {"latest": "2.0.0"}})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await scheduler.check_watchlist_now(
            session=None,
            scan_manager=manager,
            client=client,
            auto_scan=False,
        )
        assert res.checked_count == 8
        # Max active concurrent tasks must never exceed DEFAULT_MAX_CONCURRENCY
        assert max_active <= DEFAULT_MAX_CONCURRENCY


async def test_scan_cancellation_and_resource_cleanup(tmp_path: Path) -> None:
    """Verify that cancelling a scan cleans up temporary work directory without resource leaks."""
    base_dir = tmp_path / "cancellation_test"
    work_dir = base_dir / "slow_scan"

    files = {"package.json": manifest(name="slow-pkg", version="1.0.0")}
    adapter = ConcurrencyFakeAdapter(make_metadata(name="slow-pkg"), files, delay_seconds=2.0)
    resolver = ConcurrencyFakeResolver(matched(), files)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        mock_ollama = make_mock_ollama()

        task = asyncio.create_task(
            execute_scan_pipeline(
                scan_id=uuid4(),
                ecosystem=Ecosystem.NPM,
                package_name="slow-pkg",
                version="1.0.0",
                work_dir=work_dir,
                adapter=adapter,
                resolver=resolver,  # type: ignore[arg-type]
                provenance_checker=checker,
                ai_investigator=AIInvestigator(client=mock_ollama),
                clean_artifacts_on_exit=True,
            )
        )

        # Allow pipeline to start and create directories
        await asyncio.sleep(0.05)
        assert work_dir.exists()

        # Cancel the task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Finally block must have cleaned up the work directory
        assert not work_dir.exists()


async def test_pipeline_failure_cleanup(tmp_path: Path) -> None:
    """Verify failure during download cleans up temporary directories and sets FAILED state."""
    base_dir = tmp_path / "fail_cleanup"
    files = {"package.json": manifest(name="fail-pkg", version="1.0.0")}

    manager = ScanManager(
        base_work_dir=base_dir,
        adapter_factory=lambda _: ConcurrencyFakeAdapter(
            make_metadata(name="fail-pkg"), files, fail_download=True
        ),
        resolver_factory=lambda _: ConcurrencyFakeResolver(matched(), files),
        checker_factory=lambda client: NpmProvenanceChecker(client, verifier=FakeVerifier()),
        ai_investigator_factory=lambda: AIInvestigator(client=make_mock_ollama()),
    )

    record = await manager.create_scan(
        ScanRequest(ecosystem=Ecosystem.NPM, package_name="fail-pkg", version="1.0.0")
    )

    await manager._active_tasks[record.scan_id]

    scan = manager.get_scan(record.scan_id)
    assert scan is not None
    assert scan.status == ScanState.FAILED
    assert scan.stage == ScanStage.FAILED
    assert scan.error is not None
    assert "Simulated network/disk failure" in scan.error

    # Directory was cleaned up
    work_dir = base_dir / str(record.scan_id)
    assert not work_dir.exists()


async def test_ollama_timeout_graceful_handling(tmp_path: Path) -> None:
    """Verify Ollama timeouts fail gracefully without compromising deterministic findings."""
    work_dir = tmp_path / "timeout_test"
    package_files = {
        "package.json": manifest(name="timeout-pkg", version="1.0.0"),
        "index.js": "eval(process.env.SECRET);",
    }
    source_files = {
        "package.json": manifest(name="timeout-pkg", version="1.0.0"),
        "index.js": "console.log('clean');",
    }
    adapter = ConcurrencyFakeAdapter(make_metadata(name="timeout-pkg"), package_files)
    resolver = ConcurrencyFakeResolver(matched(), source_files)

    mock_ollama = AsyncMock(spec=OllamaClient)
    mock_ollama.model = "qwen2.5-coder:7b"
    mock_ollama.chat_json.side_effect = httpx.TimeoutException("Read timed out after 30.0s")

    investigator = AIInvestigator(client=mock_ollama)

    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        checker = NpmProvenanceChecker(client, verifier=FakeVerifier())
        report = await execute_scan_pipeline(
            scan_id=uuid4(),
            ecosystem=Ecosystem.NPM,
            package_name="timeout-pkg",
            version="1.0.0",
            work_dir=work_dir,
            adapter=adapter,
            resolver=resolver,  # type: ignore[arg-type]
            provenance_checker=checker,
            ai_investigator=investigator,
            clean_artifacts_on_exit=True,
        )

        assert report.status == ScanState.COMPLETED
        # Deterministic risk and findings are preserved
        assert report.risk is not None
        assert report.risk.score > 0
        assert report.security is not None
        assert len(report.security.findings) > 0

        # AI investigation gracefully records UNAVAILABLE or FAILED status
        assert report.ai is not None
        assert report.ai.status in (AIInvestigationStatus.UNAVAILABLE, AIInvestigationStatus.FAILED)
        assert "timed out" in report.ai.summary.lower()


async def test_external_api_rate_limit_behavior(tmp_path: Path) -> None:
    """Verify HTTP 429 Rate Limits from external APIs are caught and marked FAILED."""
    base_dir = tmp_path / "rate_limit_test"
    files = {"package.json": manifest(name="rate-limit-pkg", version="1.0.0")}

    manager = ScanManager(
        base_work_dir=base_dir,
        adapter_factory=lambda _: ConcurrencyFakeAdapter(
            make_metadata(name="rate-limit-pkg"), files, rate_limit=True
        ),
        resolver_factory=lambda _: ConcurrencyFakeResolver(matched(), files),
        checker_factory=lambda client: NpmProvenanceChecker(client, verifier=FakeVerifier()),
        ai_investigator_factory=lambda: AIInvestigator(client=make_mock_ollama()),
    )

    record = await manager.create_scan(
        ScanRequest(ecosystem=Ecosystem.NPM, package_name="rate-limit-pkg", version="1.0.0")
    )

    await manager._active_tasks[record.scan_id]

    scan = manager.get_scan(record.scan_id)
    assert scan is not None
    assert scan.status == ScanState.FAILED
    assert scan.error is not None
    assert "429" in scan.error or "Rate limit" in scan.error
