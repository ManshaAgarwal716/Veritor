"""Tests for database persistence and repository layer."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.repository import ScanRepository
from app.schemas.scans import (
    Ecosystem,
    ScanReportResponse,
    ScanStage,
    ScanState,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_package_and_version_creation(db_session):
    repo = ScanRepository(db_session)
    pkg = repo.get_or_create_package("pypi", "requests")
    db_session.commit()

    assert pkg.id is not None
    assert pkg.name == "requests"
    assert pkg.ecosystem == "pypi"

    # Subsequent call returns same package
    pkg_again = repo.get_or_create_package("pypi", "requests")
    assert pkg_again.id == pkg.id

    # Create version
    ver = repo.get_or_create_version(
        package_id=pkg.id,
        version="2.31.0",
        source_repo_url="https://github.com/psf/requests",
        source_commit="abcdef1234567890",
    )
    db_session.commit()

    assert ver.id is not None
    assert ver.version == "2.31.0"
    assert ver.source_repo_url == "https://github.com/psf/requests"

    # Subsequent call returns same version
    ver_again = repo.get_or_create_version(package_id=pkg.id, version="2.31.0")
    assert ver_again.id == ver.id


def test_save_and_retrieve_scan(db_session):
    repo = ScanRepository(db_session)
    scan_id = uuid.uuid4()
    now = datetime.now(UTC)

    scan = repo.save_scan(
        scan_id=scan_id,
        ecosystem="npm",
        package_name="test-lib",
        version="1.0.0",
        status=ScanState.RUNNING.value,
        stage=ScanStage.COMPARING.value,
        progress_percent=50,
        message="Comparing source to package",
        created_at=now,
    )
    db_session.commit()

    assert scan.id == scan_id
    assert scan.progress_percent == 50

    # Retrieve scan
    retrieved = repo.get_scan(scan_id)
    assert retrieved is not None
    assert retrieved.package_name == "test-lib"
    assert retrieved.status == ScanState.RUNNING.value

    # Update scan
    repo.save_scan(
        scan_id=scan_id,
        ecosystem="npm",
        package_name="test-lib",
        version="1.0.0",
        status=ScanState.COMPLETED.value,
        stage=ScanStage.COMPLETED.value,
        progress_percent=100,
        message="Scan completed successfully",
        created_at=now,
        completed_at=now,
    )
    db_session.commit()

    retrieved2 = repo.get_scan(scan_id)
    assert retrieved2 is not None
    assert retrieved2.status == ScanState.COMPLETED.value
    assert retrieved2.progress_percent == 100


def test_save_and_retrieve_scan_report(db_session):
    repo = ScanRepository(db_session)
    scan_id = uuid.uuid4()
    now = datetime.now(UTC)

    # First save scan
    repo.save_scan(
        scan_id=scan_id,
        ecosystem="pypi",
        package_name="cryptography",
        version="42.0.0",
        status=ScanState.COMPLETED.value,
        stage=ScanStage.COMPLETED.value,
        progress_percent=100,
        message="Scan complete",
        created_at=now,
    )
    db_session.commit()

    report_response = ScanReportResponse(
        scan_id=scan_id,
        ecosystem=Ecosystem.PYPI,
        package_name="cryptography",
        version="42.0.0",
        status=ScanState.COMPLETED,
        created_at=now,
        completed_at=now,
        duration_seconds=3.2,
        metadata={
            "name": "cryptography",
            "version": "42.0.0",
            "description": "Cryptography library",
        },
        source_match={
            "status": "MATCHED",
            "repository": "https://github.com/pyca/cryptography",
        },
        risk={
            "score": 15,
            "level": "LOW",
            "confidence": "HIGH",
            "completeness": "COMPLETE",
            "summary": "Low risk package",
        },
        comparison={
            "files": [
                {
                    "path": "cryptography/hazmat/bindings.py",
                    "status": "ADDED",
                    "diff_status": "UNEXPECTED_DIFF",
                    "unified": "+ # added file\n",
                    "added_lines": 1,
                    "removed_lines": 0,
                }
            ]
        },
        security={
            "findings": [
                {
                    "rule_id": "SEC-001",
                    "path": "cryptography/hazmat/bindings.py",
                    "line": 10,
                    "severity": "LOW",
                    "confidence": 0.9,
                    "evidence": "importlib.import_module",
                    "explanation": "Dynamic import detected",
                    "recommended_action": "Verify usage",
                }
            ]
        },
        provenance={
            "status": "VERIFIED",
            "sigstore_verified": True,
            "repository_matched": True,
            "commit_matched": True,
        },
        ai={
            "explanations": [
                {
                    "finding_rule_id": "SEC-001",
                    "file_path": "cryptography/hazmat/bindings.py",
                    "assessment": "BENIGN",
                    "reason": "Standard Python dynamic binding",
                    "false_positive_likelihood": 0.95,
                }
            ]
        },
    )

    # Save report
    report_model = repo.save_report(scan_id, report_response)
    db_session.commit()

    assert report_model.scan_id == scan_id
    assert report_model.risk_score == 15
    assert report_model.risk_level == "LOW"

    # Reopen report
    loaded_report = repo.get_report(scan_id)
    assert loaded_report is not None
    assert loaded_report.package_name == "cryptography"
    assert loaded_report.risk["score"] == 15

    # Check file comparisons stored in DB
    file_diff = repo.get_file_diff(scan_id, "cryptography/hazmat/bindings.py")
    assert file_diff is not None
    assert file_diff.added_lines == 1
    assert file_diff.diff_status == "UNEXPECTED_DIFF"


def test_watchlist_operations(db_session):
    repo = ScanRepository(db_session)

    # Add entries
    e1 = repo.add_watchlist_entry("npm", "react", "Core frontend dependency")
    e2 = repo.add_watchlist_entry("pypi", "flask", "Web framework")
    db_session.commit()

    assert e1.id == "npm:react"
    assert e2.id == "pypi:flask"

    # Retrieve all
    watchlist = repo.get_watchlist()
    assert len(watchlist) == 2
    ids = {entry.id for entry in watchlist}
    assert "npm:react" in ids
    assert "pypi:flask" in ids

    # Remove entry
    removed = repo.remove_watchlist_entry("npm:react")
    db_session.commit()
    assert removed is True

    # Confirm removal
    watchlist_after = repo.get_watchlist()
    assert len(watchlist_after) == 1
    assert watchlist_after[0].id == "pypi:flask"
