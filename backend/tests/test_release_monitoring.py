"""Tests for package release monitoring, update detection, and release comparison."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.repository import ScanRepository
from app.monitoring.comparator import compare_releases
from app.monitoring.detector import check_package_update, fetch_latest_version, is_newer_version
from app.monitoring.scheduler import ReleaseMonitoringScheduler
from app.scans.manager import ScanManager
from app.schemas.scans import (
    Ecosystem,
    ScanReportResponse,
    ScanState,
)

pytestmark = pytest.mark.anyio


def test_is_newer_version() -> None:
    assert is_newer_version("1.1.0", "1.0.0") is True
    assert is_newer_version("2.0.0", "1.9.9") is True
    assert is_newer_version("1.0.1", "1.0.0") is True
    assert is_newer_version("1.0.0", "1.0.0") is False
    assert is_newer_version("0.9.0", "1.0.0") is False
    assert is_newer_version("1.0.0", None) is True


async def test_fetch_latest_version_npm() -> None:
    package_data = {
        "name": "left-pad",
        "dist-tags": {"latest": "1.3.0"},
        "time": {
            "1.0.0": "2015-01-01T00:00:00Z",
            "1.3.0": "2018-05-01T00:00:00Z",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "left-pad" in request.url.path:
            return httpx.Response(200, json=package_data)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        latest = await fetch_latest_version(client, Ecosystem.NPM, "left-pad")
        assert latest == "1.3.0"

        has_update, new_ver = await check_package_update(client, Ecosystem.NPM, "left-pad", "1.2.0")
        assert has_update is True
        assert new_ver == "1.3.0"

        has_update_curr, _ = await check_package_update(client, Ecosystem.NPM, "left-pad", "1.3.0")
        assert has_update_curr is False


async def test_fetch_latest_version_pypi() -> None:
    package_data = {
        "info": {
            "name": "requests",
            "version": "2.31.0",
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "requests" in request.url.path:
            return httpx.Response(200, json=package_data)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        latest = await fetch_latest_version(client, Ecosystem.PYPI, "requests")
        assert latest == "2.31.0"

        has_update, new_ver = await check_package_update(
            client, Ecosystem.PYPI, "requests", "2.28.0"
        )
        assert has_update is True
        assert new_ver == "2.31.0"


def test_compare_releases_logic() -> None:
    now = datetime.now(UTC)
    base_id = uuid4()
    head_id = uuid4()

    base_report = ScanReportResponse(
        scan_id=base_id,
        ecosystem=Ecosystem.NPM,
        package_name="demo-lib",
        version="1.0.0",
        status=ScanState.COMPLETED,
        created_at=now,
        risk={"score": 10, "level": "LOW", "summary": "Low risk initial release"},
        comparison={
            "files": [
                {"path": "index.js", "status": "IDENTICAL", "classification": "SOURCE_AUTHENTIC"},
                {
                    "path": "lib/utils.js",
                    "status": "IDENTICAL",
                    "classification": "SOURCE_AUTHENTIC",
                },
            ]
        },
        security={"findings": []},
        provenance={"status": "VERIFIED"},
    )

    head_report = ScanReportResponse(
        scan_id=head_id,
        ecosystem=Ecosystem.NPM,
        package_name="demo-lib",
        version="1.1.0",
        status=ScanState.COMPLETED,
        created_at=now,
        risk={"score": 55, "level": "MEDIUM", "summary": "Elevated risk in new release"},
        comparison={
            "files": [
                {"path": "index.js", "status": "IDENTICAL", "classification": "SOURCE_AUTHENTIC"},
                {
                    "path": "lib/utils.js",
                    "status": "MODIFIED",
                    "unified": "+ diff",
                    "classification": "SOURCE_AUTHENTIC",
                },
                {"path": "postinstall.js", "status": "ADDED", "classification": "SUSPICIOUS"},
            ]
        },
        security={
            "findings": [
                {
                    "rule_id": "EXEC-001",
                    "path": "postinstall.js",
                    "line": 12,
                    "severity": "HIGH",
                    "evidence": "eval(code)",
                }
            ]
        },
        provenance={"status": "NOT_VERIFIED"},
    )

    comp = compare_releases(head_report, base_report)

    assert comp.package_name == "demo-lib"
    assert comp.base_version == "1.0.0"
    assert comp.head_version == "1.1.0"
    assert comp.risk_change.base_score == 10
    assert comp.risk_change.head_score == 55
    assert comp.risk_change.score_delta == 45
    assert comp.risk_change.is_elevated is True

    # Files
    assert "postinstall.js" in comp.file_changes.newly_added
    assert "lib/utils.js" in comp.file_changes.newly_modified
    assert "postinstall.js" in comp.file_changes.new_suspicious_artifacts

    # Findings
    assert len(comp.finding_changes.new_findings) == 1
    assert comp.finding_changes.new_findings[0]["rule_id"] == "EXEC-001"

    # Provenance
    assert comp.provenance_change.base_status == "VERIFIED"
    assert comp.provenance_change.head_status == "NOT_VERIFIED"
    assert comp.provenance_change.is_downgraded is True

    # Summary
    assert "Risk score increased from 10 (LOW) to 55 (MEDIUM) [delta: +45]" in comp.summary
    assert "new suspicious artifact" in comp.summary


async def test_release_monitoring_scheduler_check(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Setup watchlist entry in DB
    with session_factory() as session:
        repo = ScanRepository(session)
        entry = repo.add_watchlist_entry("npm", "chalk", "Terminal styling library")
        entry.last_scanned_version = "4.0.0"
        session.commit()

    manager = ScanManager(base_work_dir=tmp_path / "scans", session_factory=session_factory)
    scheduler = ReleaseMonitoringScheduler(request_delay_seconds=0.0)

    # Mock npm registry returning newer version 5.3.0
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"dist-tags": {"latest": "5.3.0"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with session_factory() as session:
            res = await scheduler.check_watchlist_now(
                session=session,
                scan_manager=manager,
                client=client,
                auto_scan=True,
            )

            assert res.checked_count == 1
            assert res.updates_detected == 1
            assert res.scans_triggered == 1

        # Verify entry in DB is updated
        with session_factory() as session:
            repo = ScanRepository(session)
            entries = repo.get_watchlist()
            assert len(entries) == 1
            assert entries[0].has_update is True
            assert entries[0].latest_version == "5.3.0"
            assert entries[0].last_checked_at is not None

    # Status check
    status = scheduler.get_status(total_monitored=1)
    assert status.monitored_packages_count == 1
    assert status.last_check_results is not None
    assert status.last_check_results["updates_detected"] == 1


async def test_release_monitoring_in_memory_mode(tmp_path: Path) -> None:
    """Verify monitoring functions properly when running in-memory without a database."""
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    entry = manager.add_watchlist_entry("npm", "chalk", "In-memory test package")
    entry["last_scanned_version"] = "4.0.0"

    scheduler = ReleaseMonitoringScheduler(request_delay_seconds=0.0, max_concurrency=2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"dist-tags": {"latest": "5.3.0"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await scheduler.check_watchlist_now(
            session=None,
            scan_manager=manager,
            client=client,
            auto_scan=True,
        )

        assert res.checked_count == 1
        assert res.updates_detected == 1
        assert res.scans_triggered == 1

        entries = manager.get_watchlist()
        assert len(entries) == 1
        assert entries[0]["has_update"] is True
        assert entries[0]["latest_version"] == "5.3.0"
        assert entries[0]["last_checked_at"] is not None


async def test_scheduler_prevents_duplicate_scans(tmp_path: Path) -> None:
    """Verify that multiple checks for the same latest version do not trigger duplicate scans."""
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    entry = manager.add_watchlist_entry("npm", "lodash", "Utility library")
    entry["last_scanned_version"] = "4.17.20"

    scheduler = ReleaseMonitoringScheduler(request_delay_seconds=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"dist-tags": {"latest": "4.17.21"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # First check triggers the scan
        res1 = await scheduler.check_watchlist_now(
            session=None,
            scan_manager=manager,
            client=client,
            auto_scan=True,
        )
        assert res1.scans_triggered == 1
        assert res1.details[0]["scan_triggered"] is True

        # Second check detects the update but skips re-triggering duplicate scan
        res2 = await scheduler.check_watchlist_now(
            session=None,
            scan_manager=manager,
            client=client,
            auto_scan=True,
        )
        assert res2.scans_triggered == 0
        assert res2.details[0]["duplicate_skipped"] is True


async def test_scheduler_check_lock() -> None:
    """Verify scheduler lock prevents concurrent overlapping checks."""
    import asyncio

    scheduler = ReleaseMonitoringScheduler(request_delay_seconds=0.0)

    # Acquire the lock to simulate an active running check
    assert not scheduler._check_lock.locked()
    async with scheduler._check_lock:
        assert scheduler._check_lock.locked()
        # Verify another acquisition would block
        lock_task = asyncio.create_task(scheduler._check_lock.acquire())
        done, _ = await asyncio.wait([lock_task], timeout=0.05)
        assert len(done) == 0
        assert not lock_task.done()

    # After releasing lock, task can acquire it
    await lock_task
    scheduler._check_lock.release()

