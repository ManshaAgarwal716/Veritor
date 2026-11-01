"""Scan state management and async orchestration with database persistence."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.npm import NpmAdapter
from app.adapters.pypi import PyPIAdapter
from app.ai.client import OllamaClient
from app.ai.investigator import AIInvestigator
from app.config import Settings, get_settings
from app.db.repository import ScanRepository
from app.db.session import get_session_factory
from app.provenance.npm import NpmProvenanceChecker
from app.provenance.pypi import PyPIProvenanceChecker
from app.scans.models import ScanRecord
from app.scans.pipeline import execute_scan_pipeline
from app.schemas.scans import (
    Ecosystem,
    FileDiffItem,
    ScanDiffsResponse,
    ScanFilesResponse,
    ScanFindingsResponse,
    ScanReportResponse,
    ScanRequest,
    ScanStage,
    ScanState,
    ScanStatusResponse,
)
from app.source.github import GitHubSourceResolver

logger = logging.getLogger(__name__)


class ScanNotFoundError(Exception):
    """Scan ID does not exist."""


class ScanNotReadyError(Exception):
    """Scan is still in progress."""


class ScanManager:
    """Manages scan lifecycle, asynchronous execution, and persistent state."""

    def __init__(
        self,
        settings: Settings | None = None,
        base_work_dir: Path | None = None,
        adapter_factory: Any = None,
        resolver_factory: Any = None,
        checker_factory: Any = None,
        ai_investigator_factory: Any = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_work_dir = base_work_dir or Path(gettempdir()) / "veritor_scans"
        self._scans: dict[UUID, ScanRecord] = {}
        self._lock = asyncio.Lock()
        self._adapter_factory = adapter_factory
        self._resolver_factory = resolver_factory
        self._checker_factory = checker_factory
        self._ai_investigator_factory = ai_investigator_factory
        self._session_factory = session_factory or get_session_factory()
        self._active_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._in_memory_watchlist: dict[str, dict[str, Any]] = {}

    def _get_repo(self, session: Session) -> ScanRepository:
        return ScanRepository(session)

    async def create_scan(self, request: ScanRequest) -> ScanRecord:
        """Create a new scan record and trigger background processing."""
        scan_id = uuid4()
        now = datetime.now(UTC)
        record = ScanRecord(
            scan_id=scan_id,
            ecosystem=request.ecosystem,
            package_name=request.package_name,
            version=request.version,
            status=ScanState.ACCEPTED,
            stage=ScanStage.QUEUED,
            progress_percent=0,
            message="Scan accepted and queued for processing",
            created_at=now,
        )

        async with self._lock:
            self._scans[scan_id] = record

        # Persist to DB if configured
        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    repo.save_scan(
                        scan_id=scan_id,
                        ecosystem=request.ecosystem.value,
                        package_name=request.package_name,
                        version=request.version,
                        status=ScanState.ACCEPTED.value,
                        stage=ScanStage.QUEUED.value,
                        progress_percent=0,
                        message="Scan accepted and queued for processing",
                        created_at=now,
                    )
                    session.commit()
            except Exception as exc:
                logger.warning("Could not persist initial scan %s to DB: %s", scan_id, exc)

        # Launch background task
        task = asyncio.create_task(self._run_scan(scan_id))
        self._active_tasks[scan_id] = task

        logger.info(
            "Scan created scan_id=%s ecosystem=%s package=%s version=%s",
            scan_id,
            request.ecosystem.value,
            request.package_name,
            request.version,
        )
        return record

    async def _run_scan(self, scan_id: UUID) -> None:
        record = self._scans[scan_id]
        record.status = ScanState.RUNNING
        record.started_at = datetime.now(UTC)

        work_dir = self.base_work_dir / str(scan_id)
        record.work_dir = work_dir

        async def on_progress(stage: ScanStage, percent: int, msg: str) -> None:
            record.stage = stage
            record.progress_percent = percent
            record.message = msg
            logger.debug("Scan %s progress: [%s] %d%% - %s", scan_id, stage.value, percent, msg)

            if self._session_factory:
                try:
                    with self._session_factory() as session:
                        repo = self._get_repo(session)
                        repo.save_scan(
                            scan_id=scan_id,
                            ecosystem=record.ecosystem.value,
                            package_name=record.package_name,
                            version=record.version,
                            status=record.status.value,
                            stage=stage.value,
                            progress_percent=percent,
                            message=msg,
                            created_at=record.created_at,
                            started_at=record.started_at,
                        )
                        session.commit()
                except Exception as exc:
                    logger.debug("Could not update progress in DB for scan %s: %s", scan_id, exc)

        try:
            read_timeout = self.settings.registry_read_timeout_seconds
            async with httpx.AsyncClient(timeout=read_timeout) as client:
                # 1. Resolve adapter and provenance checker based on ecosystem
                if record.ecosystem is Ecosystem.NPM:
                    adapter = (
                        self._adapter_factory(client)
                        if self._adapter_factory
                        else NpmAdapter(client, limits=self.settings.registry_limits())
                    )
                    checker = (
                        self._checker_factory(client)
                        if self._checker_factory
                        else NpmProvenanceChecker(client)
                    )
                elif record.ecosystem is Ecosystem.PYPI:
                    adapter = (
                        self._adapter_factory(client)
                        if self._adapter_factory
                        else PyPIAdapter(client, limits=self.settings.registry_limits())
                    )
                    checker = (
                        self._checker_factory(client)
                        if self._checker_factory
                        else PyPIProvenanceChecker(client)
                    )
                else:
                    raise NotImplementedError(
                        f"Ecosystem {record.ecosystem.value} adapter is not implemented yet"
                    )

                resolver = (
                    self._resolver_factory(client)
                    if self._resolver_factory
                    else GitHubSourceResolver(
                        client,
                        limits=self.settings.registry_limits(),
                        token=self.settings.github_token,
                    )
                )

                ai_investigator = (
                    self._ai_investigator_factory()
                    if self._ai_investigator_factory
                    else AIInvestigator(
                        OllamaClient(
                            base_url=self.settings.ollama_base_url,
                            model=self.settings.explain_model,
                        )
                    )
                )

                report = await execute_scan_pipeline(
                    scan_id=scan_id,
                    ecosystem=record.ecosystem,
                    package_name=record.package_name,
                    version=record.version,
                    work_dir=work_dir,
                    adapter=adapter,
                    resolver=resolver,
                    provenance_checker=checker,
                    ai_investigator=ai_investigator,
                    on_progress=on_progress,
                    extraction_limits=self.settings.extraction_limits(),
                    comparison_limits=self.settings.comparison_limits(),
                    analysis_limits=self.settings.analysis_limits(),
                )

            record.report = report
            record.status = ScanState.COMPLETED
            record.stage = ScanStage.COMPLETED
            record.progress_percent = 100
            record.completed_at = datetime.now(UTC)
            record.message = "Scan completed successfully"
            logger.info("Scan %s completed successfully", scan_id)

            # Persist full report and scan completion to DB
            if self._session_factory:
                try:
                    with self._session_factory() as session:
                        repo = self._get_repo(session)
                        duration = (
                            (record.completed_at - record.started_at).total_seconds()
                            if record.started_at and record.completed_at
                            else None
                        )
                        repo.save_scan(
                            scan_id=scan_id,
                            ecosystem=record.ecosystem.value,
                            package_name=record.package_name,
                            version=record.version,
                            status=ScanState.COMPLETED.value,
                            stage=ScanStage.COMPLETED.value,
                            progress_percent=100,
                            message="Scan completed successfully",
                            created_at=record.created_at,
                            started_at=record.started_at,
                            completed_at=record.completed_at,
                            duration_seconds=duration,
                        )
                        repo.save_report(scan_id, report)
                        session.commit()
                except Exception as exc:
                    logger.warning("Could not persist completed scan %s to DB: %s", scan_id, exc)

        except Exception as exc:
            logger.exception("Scan %s failed: %s", scan_id, exc)
            record.status = ScanState.FAILED
            record.stage = ScanStage.FAILED
            record.completed_at = datetime.now(UTC)
            record.error = str(exc)
            record.message = f"Scan failed: {exc}"

            if self._session_factory:
                try:
                    with self._session_factory() as session:
                        repo = self._get_repo(session)
                        repo.save_scan(
                            scan_id=scan_id,
                            ecosystem=record.ecosystem.value,
                            package_name=record.package_name,
                            version=record.version,
                            status=ScanState.FAILED.value,
                            stage=ScanStage.FAILED.value,
                            progress_percent=record.progress_percent,
                            message=f"Scan failed: {exc}",
                            error=str(exc),
                            created_at=record.created_at,
                            started_at=record.started_at,
                            completed_at=record.completed_at,
                        )
                        session.commit()
                except Exception as db_exc:
                    logger.warning("Could not persist failed scan %s to DB: %s", scan_id, db_exc)

    def get_scan(self, scan_id: UUID) -> ScanRecord | None:
        """Get scan record from memory, or reopen from DB if available."""
        if scan_id in self._scans:
            return self._scans[scan_id]

        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    db_scan = repo.get_scan(scan_id)
                    if db_scan:
                        report = repo.get_report(scan_id)
                        record = ScanRecord(
                            scan_id=db_scan.id,
                            ecosystem=Ecosystem(db_scan.ecosystem),
                            package_name=db_scan.package_name,
                            version=db_scan.version,
                            status=ScanState(db_scan.status),
                            stage=ScanStage(db_scan.stage),
                            progress_percent=db_scan.progress_percent,
                            message=db_scan.message,
                            error=db_scan.error,
                            created_at=db_scan.created_at,
                            started_at=db_scan.started_at,
                            completed_at=db_scan.completed_at,
                            report=report,
                        )
                        self._scans[scan_id] = record
                        return record
            except Exception as exc:
                logger.warning("Error reopening scan %s from DB: %s", scan_id, exc)

        return None

    def get_status(self, scan_id: UUID) -> ScanStatusResponse:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        return ScanStatusResponse(
            scan_id=record.scan_id,
            ecosystem=record.ecosystem,
            package_name=record.package_name,
            version=record.version,
            status=record.status,
            stage=record.stage,
            progress_percent=record.progress_percent,
            message=record.message,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error=record.error,
        )

    def get_report(self, scan_id: UUID) -> ScanReportResponse:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        if record.status in (ScanState.ACCEPTED, ScanState.RUNNING):
            raise ScanNotReadyError(f"Scan {scan_id} is still {record.status.value}")
        if record.report is not None:
            return record.report

        # If report not in record, try reloading directly from DB
        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    db_report = repo.get_report(scan_id)
                    if db_report:
                        record.report = db_report
                        return db_report
            except Exception as exc:
                logger.warning("Error fetching report for scan %s from DB: %s", scan_id, exc)

        # Fallback if failed without report
        return ScanReportResponse(
            scan_id=record.scan_id,
            ecosystem=record.ecosystem,
            package_name=record.package_name,
            version=record.version,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error=record.error,
        )

    def get_findings(self, scan_id: UUID) -> ScanFindingsResponse:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        if record.status in (ScanState.ACCEPTED, ScanState.RUNNING):
            raise ScanNotReadyError(f"Scan {scan_id} is still {record.status.value}")

        report = record.report
        if report is None:
            return ScanFindingsResponse(
                scan_id=record.scan_id,
                package_name=record.package_name,
                version=record.version,
            )

        findings = list(report.security.findings) if report.security else []
        gaps = list(report.security.gaps) if report.security else []
        ai_explanations = list(report.ai.explanations) if report.ai else []
        factors = list(report.risk.factors) if report.risk else []
        floors = list(report.risk.floors) if report.risk else []
        score = report.risk.score if report.risk else None
        level = (
            report.risk.level.name
            if report.risk and hasattr(report.risk.level, "name")
            else (report.risk.level if report.risk else None)
        )

        return ScanFindingsResponse(
            scan_id=record.scan_id,
            package_name=record.package_name,
            version=record.version,
            risk_score=score,
            risk_level=level,
            findings=findings,
            ai_explanations=ai_explanations,
            gaps=gaps,
            factors=factors,
            floors=floors,
        )

    def get_files(self, scan_id: UUID) -> ScanFilesResponse:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        if record.status in (ScanState.ACCEPTED, ScanState.RUNNING):
            raise ScanNotReadyError(f"Scan {scan_id} is still {record.status.value}")

        report = record.report
        summary = report.comparison.summary if report and report.comparison else None
        files = list(report.comparison.files) if report and report.comparison else []

        return ScanFilesResponse(
            scan_id=record.scan_id,
            package_name=record.package_name,
            version=record.version,
            summary=summary,
            files=files,
        )

    def get_diffs(self, scan_id: UUID, path: str | None = None) -> ScanDiffsResponse:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        if record.status in (ScanState.ACCEPTED, ScanState.RUNNING):
            raise ScanNotReadyError(f"Scan {scan_id} is still {record.status.value}")

        report = record.report
        diff_items: list[FileDiffItem] = []

        if report and report.comparison:
            for file_comp in report.comparison.files:
                p = getattr(file_comp, "path", None)
                pkg_p = getattr(file_comp, "package_path", None)
                src_p = getattr(file_comp, "source_path", None)

                if path is not None and path not in (p, pkg_p, src_p):
                    continue

                diff_obj = getattr(file_comp, "diff", None)
                unified = getattr(diff_obj, "unified", None) if diff_obj else None
                status_val = (
                    file_comp.status.value
                    if hasattr(file_comp.status, "value")
                    else str(file_comp.status)
                )
                diff_status_val = (
                    diff_obj.status.value
                    if diff_obj and hasattr(diff_obj.status, "value")
                    else "CLEAN"
                )
                added_lines = getattr(diff_obj, "added_lines", None) if diff_obj else None
                removed_lines = getattr(diff_obj, "removed_lines", None) if diff_obj else None

                if unified is not None or path is not None:
                    diff_items.append(
                        FileDiffItem(
                            path=p or "",
                            status=status_val,
                            diff_status=diff_status_val,
                            unified=unified,
                            added_lines=added_lines,
                            removed_lines=removed_lines,
                        )
                    )

        # Fallback to DB if empty and session available
        if not diff_items and self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    comps = repo.get_file_comparisons(scan_id)
                    for fc in comps:
                        if path is not None and fc.path != path:
                            continue
                        diff_items.append(
                            FileDiffItem(
                                path=fc.path,
                                status=fc.status,
                                diff_status=fc.diff_status,
                                unified=fc.unified_diff,
                                added_lines=fc.added_lines,
                                removed_lines=fc.removed_lines,
                            )
                        )
            except Exception as exc:
                logger.warning("Error fetching diffs for scan %s from DB: %s", scan_id, exc)

        return ScanDiffsResponse(
            scan_id=record.scan_id,
            package_name=record.package_name,
            version=record.version,
            total_diffs=len(diff_items),
            diffs=diff_items,
        )

    def get_file_diff(self, scan_id: UUID, file_id: str) -> FileDiffItem:
        record = self.get_scan(scan_id)
        if record is None:
            raise ScanNotFoundError(f"Scan {scan_id} not found")
        if record.status in (ScanState.ACCEPTED, ScanState.RUNNING):
            raise ScanNotReadyError(f"Scan {scan_id} is still {record.status.value}")

        report = record.report
        matched_item = None

        if report and report.comparison and report.comparison.files:
            if file_id.isdigit():
                idx = int(file_id)
                if 0 <= idx < len(report.comparison.files):
                    matched_item = report.comparison.files[idx]

            if matched_item is None:
                for file_comp in report.comparison.files:
                    p = getattr(file_comp, "path", None)
                    pkg_p = getattr(file_comp, "package_path", None)
                    src_p = getattr(file_comp, "source_path", None)
                    if file_id in (p, pkg_p, src_p):
                        matched_item = file_comp
                        break

        if matched_item is not None:
            diff_obj = getattr(matched_item, "diff", None)
            return FileDiffItem(
                path=matched_item.path,
                status=(
                    matched_item.status.value
                    if hasattr(matched_item.status, "value")
                    else str(matched_item.status)
                ),
                diff_status=(
                    diff_obj.status.value
                    if diff_obj and hasattr(diff_obj.status, "value")
                    else "CLEAN"
                ),
                unified=getattr(diff_obj, "unified", None) if diff_obj else None,
                added_lines=getattr(diff_obj, "added_lines", None) if diff_obj else None,
                removed_lines=getattr(diff_obj, "removed_lines", None) if diff_obj else None,
            )

        # Fallback to DB
        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    diff_item = repo.get_file_diff(scan_id, file_id)
                    if diff_item:
                        return diff_item
            except Exception as exc:
                logger.warning("Error fetching file diff for %s from DB: %s", file_id, exc)

        raise ScanNotFoundError(f"File {file_id!r} not found in scan comparison")

    # Watchlist Management
    def get_watchlist(self) -> list[dict[str, Any]]:
        """Retrieve watchlist entries from DB or memory."""
        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    entries = repo.get_watchlist()
                    return [
                        {
                            "id": e.id,
                            "ecosystem": e.ecosystem,
                            "package_name": e.package_name,
                            "notes": e.notes,
                            "last_scanned_version": e.last_scanned_version,
                            "last_risk_score": e.last_risk_score,
                            "last_risk_level": e.last_risk_level,
                            "created_at": e.created_at.isoformat() if e.created_at else None,
                        }
                        for e in entries
                    ]
            except Exception as exc:
                logger.warning("Error retrieving watchlist from DB: %s", exc)

        return list(self._in_memory_watchlist.values())

    def add_watchlist_entry(
        self, ecosystem: str, package_name: str, notes: str | None = None
    ) -> dict[str, Any]:
        """Add package to watchlist."""
        entry_id = f"{ecosystem}:{package_name}"
        item: dict[str, Any] = {
            "id": entry_id,
            "ecosystem": ecosystem,
            "package_name": package_name,
            "notes": notes,
            "created_at": datetime.now(UTC).isoformat(),
        }

        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    e = repo.add_watchlist_entry(ecosystem, package_name, notes)
                    session.commit()
                    item["created_at"] = (
                        e.created_at.isoformat() if e.created_at else item["created_at"]
                    )
                    return item
            except Exception as exc:
                logger.warning("Error saving watchlist entry to DB: %s", exc)

        self._in_memory_watchlist[entry_id] = item
        return item

    def remove_watchlist_entry(self, entry_id: str) -> bool:
        """Remove package from watchlist."""
        if self._session_factory:
            try:
                with self._session_factory() as session:
                    repo = self._get_repo(session)
                    result = repo.remove_watchlist_entry(entry_id)
                    session.commit()
                    if result:
                        self._in_memory_watchlist.pop(entry_id, None)
                        return True
            except Exception as exc:
                logger.warning("Error deleting watchlist entry from DB: %s", exc)

        if entry_id in self._in_memory_watchlist:
            del self._in_memory_watchlist[entry_id]
            return True
        return False


_scan_manager: ScanManager | None = None


def get_scan_manager() -> ScanManager:
    global _scan_manager
    if _scan_manager is None:
        _scan_manager = ScanManager()
    return _scan_manager


def set_scan_manager(manager: ScanManager | None) -> None:
    global _scan_manager
    _scan_manager = manager
