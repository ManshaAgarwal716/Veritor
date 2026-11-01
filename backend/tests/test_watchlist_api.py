"""Tests for watchlist REST API endpoints and scan comparison."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scans.manager import ScanManager, set_scan_manager
from app.scans.models import ScanRecord
from app.schemas.scans import (
    Ecosystem,
    ScanReportResponse,
    ScanStage,
    ScanState,
)


@pytest.fixture
def test_setup(tmp_path: Path) -> tuple[ScanManager, TestClient]:
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    set_scan_manager(manager)
    client = TestClient(app)
    return manager, client


def test_watchlist_crud_endpoints(test_setup: tuple[ScanManager, TestClient]) -> None:
    manager, client = test_setup

    # 1. Initially empty
    res = client.get("/api/v1/watchlist")
    assert res.status_code == 200
    assert res.json() == []

    # 2. Add entry
    payload = {
        "ecosystem": "npm",
        "package_name": "express",
        "notes": "Web framework",
    }
    res_add = client.post("/api/v1/watchlist", json=payload)
    assert res_add.status_code == 201
    data = res_add.json()
    assert data["id"] == "npm:express"
    assert data["package_name"] == "express"
    assert data["ecosystem"] == "npm"
    assert data["notes"] == "Web framework"

    # 3. List contains added entry
    res_list = client.get("/api/v1/watchlist")
    assert res_list.status_code == 200
    entries = res_list.json()
    assert len(entries) == 1
    assert entries[0]["id"] == "npm:express"

    # 4. Remove entry
    res_del = client.delete("/api/v1/watchlist/npm:express")
    assert res_del.status_code == 204

    # 5. List is empty again
    res_list_after = client.get("/api/v1/watchlist")
    assert res_list_after.status_code == 200
    assert res_list_after.json() == []


def test_watchlist_check_and_status(test_setup: tuple[ScanManager, TestClient]) -> None:
    manager, client = test_setup

    # Check status
    res_status = client.get("/api/v1/watchlist/monitoring-status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "is_running" in status_data
    assert "interval_seconds" in status_data

    # Check on-demand updates
    res_check = client.post("/api/v1/watchlist/check")
    assert res_check.status_code == 200
    check_data = res_check.json()
    assert "checked_count" in check_data
    assert "updates_detected" in check_data


def test_release_comparison_endpoints(test_setup: tuple[ScanManager, TestClient]) -> None:
    manager, client = test_setup
    now = datetime.now(UTC)

    # Create two completed scan reports for the same package
    id_v1 = uuid4()
    id_v2 = uuid4()

    rep_v1 = ScanReportResponse(
        scan_id=id_v1,
        ecosystem=Ecosystem.PYPI,
        package_name="flask",
        version="2.0.0",
        status=ScanState.COMPLETED,
        created_at=now,
        risk={"score": 12, "level": "LOW", "summary": "Initial baseline"},
        comparison={"files": [{"path": "app.py", "status": "IDENTICAL"}]},
        security={"findings": []},
        provenance={"status": "UNAVAILABLE"},
    )

    rep_v2 = ScanReportResponse(
        scan_id=id_v2,
        ecosystem=Ecosystem.PYPI,
        package_name="flask",
        version="2.1.0",
        status=ScanState.COMPLETED,
        created_at=now,
        risk={"score": 35, "level": "MEDIUM", "summary": "Added routes and config changes"},
        comparison={
            "files": [
                {"path": "app.py", "status": "IDENTICAL"},
                {"path": "routes.py", "status": "ADDED", "classification": "SOURCE_AUTHENTIC"},
            ]
        },
        security={"findings": []},
        provenance={"status": "UNAVAILABLE"},
    )

    rec_v1 = ScanRecord(
        scan_id=id_v1,
        ecosystem=Ecosystem.PYPI,
        package_name="flask",
        version="2.0.0",
        status=ScanState.COMPLETED,
        stage=ScanStage.COMPLETED,
        progress_percent=100,
        message="Done",
        created_at=now,
        report=rep_v1,
    )
    rec_v2 = ScanRecord(
        scan_id=id_v2,
        ecosystem=Ecosystem.PYPI,
        package_name="flask",
        version="2.1.0",
        status=ScanState.COMPLETED,
        stage=ScanStage.COMPLETED,
        progress_percent=100,
        message="Done",
        created_at=now,
        report=rep_v2,
    )

    manager._scans[id_v1] = rec_v1
    manager._scans[id_v2] = rec_v2

    # Compare by scan IDs via /api/v1/scans/compare
    res_comp = client.get(f"/api/v1/scans/compare?head_scan_id={id_v2}&base_scan_id={id_v1}")
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["package_name"] == "flask"
    assert comp_data["base_version"] == "2.0.0"
    assert comp_data["head_version"] == "2.1.0"
    assert comp_data["risk_change"]["score_delta"] == 23
    assert comp_data["risk_change"]["is_elevated"] is True
    assert "routes.py" in comp_data["file_changes"]["newly_added"]

    # Compare with previous automatically via /api/v1/scans/{scan_id}/compare-previous
    res_prev = client.get(f"/api/v1/scans/{id_v2}/compare-previous")
    assert res_prev.status_code == 200
    prev_data = res_prev.json()
    assert prev_data["package_name"] == "flask"
    assert prev_data["base_version"] == "2.0.0"
    assert prev_data["head_version"] == "2.1.0"
