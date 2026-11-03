"""Automated database migration and schema verification tests.

Addresses audit finding TST-03:
1. Alembic upgrade to head
2. Schema creation
3. Required tables and indexes
4. Foreign-key constraints and cascade deletions
5. Application database operations (ScanRepository)
6. Downgrade to base
7. Re-upgrade again after downgrade
"""

import logging
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.db.models import (
    Package,
    PackageVersion,
    Scan,
    ScanReport,
    SecurityFinding,
)
from app.db.repository import ScanRepository
from app.schemas.scans import (
    Ecosystem,
    ScanReportResponse,
    ScanStage,
    ScanState,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = REPO_ROOT / "backend" / "alembic.ini"
ALEMBIC_SCRIPT_DIR = REPO_ROOT / "backend" / "alembic"

EXPECTED_TABLES = {
    "packages",
    "package_versions",
    "scans",
    "scan_reports",
    "file_comparisons",
    "security_findings",
    "provenance_results",
    "ai_explanations",
    "watchlist_entries",
    "alembic_version",
}


def _get_postgres_admin_url() -> str | None:
    """Return a candidate PostgreSQL admin connection string if accessible."""
    candidates = [
        os.getenv("VERITOR_TEST_DATABASE_URL"),
        os.getenv("POSTGRES_TEST_DATABASE_URL"),
        "postgresql://postgres:postgres@localhost:5432/postgres",
        "postgresql://veritor:veritor@localhost:5432/postgres",
        "postgresql://veritor:veritor@localhost:5432/veritor",
    ]
    for url in candidates:
        if not url:
            continue
        # Convert sqlalchemy format to standard URI for psycopg ping
        conninfo = url.replace("postgresql+psycopg://", "postgresql://")
        try:
            conn = psycopg.connect(conninfo, connect_timeout=1)
            conn.close()
            return conninfo
        except Exception as exc:
            logger.debug("Candidate Postgres URL %s not accessible: %s", conninfo, exc)
            continue
    return None


@pytest.fixture
def isolated_postgres_db() -> Generator[tuple[Engine, Config, str], None, None]:
    """Create isolated temporary PostgreSQL database and drop it in teardown."""
    admin_url = _get_postgres_admin_url()
    if not admin_url:
        pytest.skip(
            "PostgreSQL server not accessible on port 5432. "
            "Set VERITOR_TEST_DATABASE_URL to enable PostgreSQL migration tests."
        )

    db_name = f"veritor_test_mig_{uuid.uuid4().hex[:10]}"
    admin_conn = psycopg.connect(admin_url, autocommit=True)
    cur = admin_conn.cursor()
    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    admin_conn.close()

    # Form target test URL with psycopg driver
    base_target = admin_url.rsplit("/", 1)[0]
    sa_test_url = f"{base_target}/{db_name}".replace("postgresql://", "postgresql+psycopg://")

    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", sa_test_url)
    cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_DIR))

    engine = create_engine(sa_test_url, pool_pre_ping=True)

    try:
        yield engine, cfg, sa_test_url
    finally:
        engine.dispose()
        # Disconnect any remaining sessions and drop the temporary database
        try:
            cleanup_conn = psycopg.connect(admin_url, autocommit=True)
            cleanup_cur = cleanup_conn.cursor()
            cleanup_cur.execute(
                sql.SQL(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid();
                    """
                ),
                (db_name,),
            )
            cleanup_cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name))
            )
            cleanup_conn.close()
        except Exception as exc:
            logger.warning("Error cleaning up test database %s: %s", db_name, exc)


@pytest.fixture
def isolated_sqlite_db(tmp_path: Path) -> Generator[tuple[Engine, Config, str], None, None]:
    """Create an isolated, file-based SQLite database for migration testing."""
    db_file = tmp_path / "migration_test.db"
    sa_url = f"sqlite:///{db_file}"

    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", sa_url)
    cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_DIR))

    engine = create_engine(sa_url, connect_args={"check_same_thread": False})
    try:
        yield engine, cfg, sa_url
    finally:
        engine.dispose()
        if db_file.exists():
            db_file.unlink()


# ---------------------------------------------------------------------------
# Migration Lifecycle Tests (PostgreSQL & SQLite)
# ---------------------------------------------------------------------------


def _execute_full_migration_lifecycle(engine: Engine, cfg: Config) -> None:
    """Execute complete 7-step migration verification suite."""
    # -----------------------------------------------------------------------
    # Step 1: Alembic upgrade to head
    # -----------------------------------------------------------------------
    command.upgrade(cfg, "head")

    # -----------------------------------------------------------------------
    # Step 2: Schema creation and table inventory
    # -----------------------------------------------------------------------
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"

    # -----------------------------------------------------------------------
    # Step 3: Required columns and indexes
    # -----------------------------------------------------------------------
    # Verify revision 002 release monitoring columns exist on watchlist_entries
    watchlist_cols = {col["name"]: col for col in insp.get_columns("watchlist_entries")}
    assert "latest_version" in watchlist_cols
    assert "has_update" in watchlist_cols
    assert "last_checked_at" in watchlist_cols
    assert "diff_summary_json" in watchlist_cols

    # Verify scan table columns
    scan_cols = {col["name"]: col for col in insp.get_columns("scans")}
    assert "id" in scan_cols
    assert "status" in scan_cols
    assert "stage" in scan_cols
    assert "progress_percent" in scan_cols
    assert "message" in scan_cols

    # Verify indexes
    package_indexes = {ix["name"] for ix in insp.get_indexes("packages")}
    assert "ix_packages_ecosystem_name" in package_indexes

    scan_indexes = {ix["name"] for ix in insp.get_indexes("scans")}
    assert "ix_scans_pkg_ver" in scan_indexes
    assert "ix_scans_created_at" in scan_indexes

    watchlist_indexes = {ix["name"] for ix in insp.get_indexes("watchlist_entries")}
    assert "ix_watchlist_ecosystem_package" in watchlist_indexes

    # -----------------------------------------------------------------------
    # Step 4: Foreign key constraints and cascade deletions
    # -----------------------------------------------------------------------
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        # Create hierarchy: package -> version -> scan -> report & finding
        pkg = Package(
            ecosystem="npm",
            name="test-lib",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(pkg)
        session.flush()

        ver = PackageVersion(
            package_id=pkg.id,
            version="1.0.0",
            created_at=datetime.now(UTC),
        )
        session.add(ver)
        session.flush()

        scan_id = uuid4()
        scan = Scan(
            id=scan_id,
            package_version_id=ver.id,
            ecosystem="npm",
            package_name="test-lib",
            version="1.0.0",
            status="completed",
            stage="completed",
            progress_percent=100,
            message="Completed",
            created_at=datetime.now(UTC),
        )
        session.add(scan)
        session.flush()

        report = ScanReport(
            scan_id=scan.id,
            report_json={"test": "data"},
            created_at=datetime.now(UTC),
        )
        finding = SecurityFinding(
            scan_id=scan.id,
            rule_id="EXEC-001",
            path="index.js",
            line=1,
            severity="HIGH",
            confidence="HIGH",
            evidence="eval(x)",
            explanation="Eval",
            recommended_action="Remove eval",
        )
        session.add_all([report, finding])
        session.commit()

        # Verify entities persisted
        assert session.get(Scan, scan_id) is not None
        assert session.query(ScanReport).filter_by(scan_id=scan_id).first() is not None
        assert session.query(SecurityFinding).filter_by(scan_id=scan_id).first() is not None

        # Verify cascade delete: deleting scan removes report and finding
        session.delete(scan)
        session.commit()

        assert session.query(ScanReport).filter_by(scan_id=scan_id).first() is None
        assert session.query(SecurityFinding).filter_by(scan_id=scan_id).first() is None

        # Verify FK violation: inserting report with non-existent scan_id raises error
        if engine.dialect.name == "postgresql":
            invalid_report = ScanReport(
                scan_id=uuid4(),
                report_json={"error": "foreign key test"},
                created_at=datetime.now(UTC),
            )
            session.add(invalid_report)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

    # -----------------------------------------------------------------------
    # Step 5: Application repository operations (ScanRepository)
    # -----------------------------------------------------------------------
    with session_factory() as session:
        repo = ScanRepository(session)

        # Save and retrieve a scan
        app_scan_id = uuid4()
        repo.save_scan(
            scan_id=app_scan_id,
            ecosystem="pypi",
            package_name="requests",
            version="2.32.3",
            status=ScanState.ACCEPTED.value,
            stage=ScanStage.QUEUED.value,
            progress_percent=0,
            message="Queued",
            created_at=datetime.now(UTC),
        )
        session.commit()

        loaded_scan = repo.get_scan(app_scan_id)
        assert loaded_scan is not None
        assert loaded_scan.package_name == "requests"
        assert loaded_scan.version == "2.32.3"
        assert loaded_scan.status == ScanState.ACCEPTED.value

        # Save and retrieve report
        mock_report_response = ScanReportResponse(
            scan_id=app_scan_id,
            ecosystem=Ecosystem.PYPI,
            package_name="requests",
            version="2.32.3",
            status=ScanState.COMPLETED,
            created_at=datetime.now(UTC),
        )
        repo.save_report(app_scan_id, mock_report_response)
        session.commit()

        loaded_report = repo.get_report(app_scan_id)
        assert loaded_report is not None
        assert loaded_report.scan_id == app_scan_id

        # Watchlist CRUD operations
        repo.add_watchlist_entry(
            ecosystem="pypi",
            package_name="requests",
            notes="HTTP client",
        )
        session.commit()

        watchlist = repo.get_watchlist()
        assert any(e.package_name == "requests" for e in watchlist)

        # Update watchlist entry with release monitoring data (revision 002)
        entry = repo.get_watchlist_entry("pypi:requests")
        assert entry is not None
        entry.latest_version = "2.32.3"
        entry.has_update = True
        entry.last_checked_at = datetime.now(UTC)
        entry.diff_summary_json = {"score_delta": 0, "status": "CLEAN"}
        session.commit()

        updated_entry = repo.get_watchlist_entry("pypi:requests")
        assert updated_entry is not None
        assert updated_entry.has_update is True
        assert updated_entry.latest_version == "2.32.3"

        # Remove entry
        repo.remove_watchlist_entry(updated_entry.id)
        session.commit()
        assert repo.get_watchlist_entry("pypi:requests") is None

    # -----------------------------------------------------------------------
    # Step 6: Downgrade to base
    # -----------------------------------------------------------------------
    # Partial downgrade to 001_initial_schema
    command.downgrade(cfg, "001_initial_schema")
    insp_down1 = inspect(engine)
    watchlist_cols_down = {col["name"] for col in insp_down1.get_columns("watchlist_entries")}
    assert "latest_version" not in watchlist_cols_down
    assert "has_update" not in watchlist_cols_down
    assert "diff_summary_json" not in watchlist_cols_down
    assert "id" in watchlist_cols_down

    # Full downgrade to base
    command.downgrade(cfg, "base")
    insp_base = inspect(engine)
    tables_base = set(insp_base.get_table_names())
    app_tables = tables_base - {"alembic_version"}
    assert len(app_tables) == 0, f"Tables still remaining after downgrade base: {app_tables}"

    # -----------------------------------------------------------------------
    # Step 7: Re-upgrade to head after downgrade
    # -----------------------------------------------------------------------
    command.upgrade(cfg, "head")
    insp_reup = inspect(engine)
    tables_reup = set(insp_reup.get_table_names())
    assert EXPECTED_TABLES.issubset(tables_reup)

    # Ensure application operations work on re-upgraded database
    with session_factory() as session:
        repo = ScanRepository(session)
        reup_scan_id = uuid4()
        repo.save_scan(
            scan_id=reup_scan_id,
            ecosystem="npm",
            package_name="chalk",
            version="5.3.0",
            status=ScanState.COMPLETED.value,
            stage=ScanStage.COMPLETED.value,
            progress_percent=100,
            message="Re-upgrade verification",
            created_at=datetime.now(UTC),
        )
        session.commit()

        loaded_reup = repo.get_scan(reup_scan_id)
        assert loaded_reup is not None
        assert loaded_reup.package_name == "chalk"


def test_sqlite_migration_lifecycle(
    isolated_sqlite_db: tuple[Engine, Config, str],
) -> None:
    """Test full Alembic lifecycle on isolated SQLite."""
    engine, cfg, _ = isolated_sqlite_db
    _execute_full_migration_lifecycle(engine, cfg)


def test_postgres_migration_lifecycle(
    isolated_postgres_db: tuple[Engine, Config, str],
) -> None:
    """Test full Alembic lifecycle on live PostgreSQL."""
    engine, cfg, _ = isolated_postgres_db
    _execute_full_migration_lifecycle(engine, cfg)
