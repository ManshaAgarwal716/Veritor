"""Tests for JSON and PDF report exports."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reports.json_exporter import generate_json_report
from app.reports.pdf_exporter import generate_pdf_report
from app.scans.manager import ScanManager, set_scan_manager
from app.schemas.scans import (
    Ecosystem,
    ScanReportResponse,
    ScanStage,
    ScanState,
)


@pytest.fixture
def sample_report() -> ScanReportResponse:
    scan_id = uuid4()
    now = datetime.now(UTC)
    return ScanReportResponse(
        scan_id=scan_id,
        ecosystem=Ecosystem.NPM,
        package_name="test-package",
        version="2.0.0",
        status=ScanState.COMPLETED,
        created_at=now,
        completed_at=now,
        duration_seconds=2.45,
        metadata={
            "name": "test-package",
            "version": "2.0.0",
            "description": "A demo security package",
            "license": "Apache-2.0",
            "homepage": "https://example.com/test-package",
        },
        source_match={
            "status": "MATCHED",
            "repository": "https://github.com/example/test-package",
            "commit_sha": "a" * 40,
            "method": "package_tag",
            "confidence": "HIGH",
            "tag": "v2.0.0",
        },
        comparison={
            "total_files": 3,
            "files": [
                {
                    "path": "index.js",
                    "status": "IDENTICAL",
                    "diff_status": "CLEAN",
                    "classification": "SOURCE_AUTHENTIC",
                },
                {
                    "path": "dist/bundle.js",
                    "status": "ADDED",
                    "diff_status": "UNEXPECTED_DIFF",
                    "classification": "LIKELY_GENERATED",
                },
                {
                    "path": "scripts/postinstall.js",
                    "status": "ADDED",
                    "diff_status": "UNEXPECTED_DIFF",
                    "classification": "SUSPICIOUS",
                },
            ],
        },
        security={
            "findings": [
                {
                    "rule_id": "EXEC-001",
                    "path": "scripts/postinstall.js",
                    "line": 15,
                    "severity": "CRITICAL",
                    "confidence": "HIGH",
                    "evidence": "eval(Buffer.from(...))",
                    "explanation": "Dynamic code execution in lifecycle script",
                    "recommended_action": "Audit immediately",
                }
            ],
            "gaps": [],
        },
        provenance={
            "status": "VERIFIED",
            "sigstore_verified": True,
            "package_integrity": "b" * 64,
            "tarball_digest_matches": True,
            "repository_matches_declared": True,
            "commit_matches_source_match": True,
        },
        risk={
            "score": 65,
            "level": "HIGH",
            "confidence": "HIGH",
            "completeness": "COMPLETE",
            "summary": "High risk due to suspicious lifecycle script and dynamic execution.",
            "contributing_factors": ["Suspicious postinstall script", "Dynamic eval usage"],
            "recommendations": ["Do not install without isolation"],
            "limitations": ["Minified bundles not fully decompiled"],
        },
        ai={
            "model": "qwen2.5-coder:7b",
            "status": "COMPLETED",
            "behavioral_summary": "Confirmed high likelihood of malicious supply chain injection.",
        },
    )


def test_generate_json_report(sample_report: ScanReportResponse) -> None:
    result = generate_json_report(sample_report)

    assert result["export_metadata"]["schema_version"] == "1.0.0"
    assert "report_integrity_sha256" in result["export_metadata"]
    assert len(result["export_metadata"]["report_integrity_sha256"]) == 64

    # Check overview
    assert result["scan_overview"]["package_name"] == "test-package"
    assert result["scan_overview"]["version"] == "2.0.0"

    # Check comparison stats
    stats = result["comparison_statistics"]
    assert stats["total_files"] == 3
    assert stats["identical_files_count"] == 1
    assert stats["added_files_count"] == 2
    assert stats["likely_generated_count"] == 1
    assert stats["suspicious_artifacts_count"] == 1

    # Check findings & risk
    assert len(result["security_findings"]) == 1
    assert result["security_findings"][0]["rule_id"] == "EXEC-001"
    assert result["deterministic_risk_assessment"]["score"] == 65
    assert result["deterministic_risk_assessment"]["level"] == "HIGH"
    assert result["provenance_verification"]["status"] == "VERIFIED"


def test_generate_pdf_report(sample_report: ScanReportResponse) -> None:
    pdf_bytes = generate_pdf_report(sample_report)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    # PDF specification magic header
    assert pdf_bytes.startswith(b"%PDF")


def test_export_endpoints(tmp_path: Path, sample_report: ScanReportResponse) -> None:
    manager = ScanManager(base_work_dir=tmp_path / "scans")
    set_scan_manager(manager)

    # Register report in manager
    scan_id = sample_report.scan_id
    from app.scans.models import ScanRecord

    rec = ScanRecord(
        scan_id=scan_id,
        ecosystem=sample_report.ecosystem,
        package_name=sample_report.package_name,
        version=sample_report.version,
        status=ScanState.COMPLETED,
        stage=ScanStage.COMPLETED,
        progress_percent=100,
        message="Done",
        created_at=sample_report.created_at,
        completed_at=sample_report.completed_at,
        report=sample_report,
    )
    manager._scans[scan_id] = rec

    client = TestClient(app)

    # JSON export endpoint
    res_json = client.get(f"/api/v1/scans/{scan_id}/export/json")
    assert res_json.status_code == 200
    assert res_json.headers["content-type"].startswith("application/json")
    assert "attachment" in res_json.headers["content-disposition"]
    data = res_json.json()
    assert data["scan_overview"]["package_name"] == "test-package"
    assert "report_integrity_sha256" in data["export_metadata"]

    # PDF export endpoint
    res_pdf = client.get(f"/api/v1/scans/{scan_id}/export/pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in res_pdf.headers["content-disposition"]
    assert res_pdf.content.startswith(b"%PDF")
