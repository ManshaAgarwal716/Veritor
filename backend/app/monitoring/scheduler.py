"""Scheduled background monitoring worker and rate-limited update checker."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.orm import Session

from app.db import models
from app.db.repository import ScanRepository
from app.monitoring.comparator import compare_releases
from app.monitoring.detector import check_package_update
from app.schemas.scans import Ecosystem, ScanRequest, ScanState
from app.schemas.watchlist import MonitoringStatusResponse, WatchlistCheckResponse

if TYPE_CHECKING:
    from app.scans.manager import ScanManager
else:
    try:
        from app.scans.manager import ScanManager
    except ImportError:
        ScanManager = Any

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL_SECONDS = 300
DEFAULT_REQUEST_DELAY_SECONDS = 1.0
DEFAULT_MAX_CONCURRENCY = 4


class ReleaseMonitoringScheduler:
    """Coordinates periodic checks and rate-limited detection of package releases."""

    def __init__(
        self,
        interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.request_delay_seconds = request_delay_seconds
        self.max_concurrency = max_concurrency
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_check_timestamp: str | None = None
        self._last_check_results: dict[str, Any] | None = None
        self._check_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self, total_monitored: int = 0) -> MonitoringStatusResponse:
        return MonitoringStatusResponse(
            is_running=self.is_running,
            interval_seconds=self.interval_seconds,
            monitored_packages_count=total_monitored,
            last_check_timestamp=self._last_check_timestamp,
            last_check_results=self._last_check_results,
        )

    async def check_watchlist_now(
        self,
        session: Session | None,
        scan_manager: ScanManager,
        client: httpx.AsyncClient | None = None,
        auto_scan: bool = True,
    ) -> WatchlistCheckResponse:
        """Perform a rate-limited check across all monitored watchlist packages.

        Prevents overlapping checks and supports both database and in-memory modes.
        """
        if self._check_lock.locked():
            logger.info("Watchlist check already in progress; skipping concurrent check")
            return WatchlistCheckResponse(
                checked_count=0,
                updates_detected=0,
                scans_triggered=0,
                details=[],
            )

        async with self._check_lock:
            if session is not None:
                return await self._check_database_watchlist(
                    session=session,
                    scan_manager=scan_manager,
                    client=client,
                    auto_scan=auto_scan,
                )
            return await self._check_in_memory_watchlist(
                scan_manager=scan_manager,
                client=client,
                auto_scan=auto_scan,
            )

    async def _check_database_watchlist(
        self,
        session: Session,
        scan_manager: ScanManager,
        client: httpx.AsyncClient | None,
        auto_scan: bool,
    ) -> WatchlistCheckResponse:
        repo = ScanRepository(session)
        entries = repo.get_watchlist()
        if not entries:
            return WatchlistCheckResponse(
                checked_count=0,
                updates_detected=0,
                scans_triggered=0,
                details=[],
            )

        owns_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            owns_client = True

        sem = asyncio.Semaphore(self.max_concurrency)
        checked_count = 0
        updates_detected = 0
        scans_triggered = 0
        details: list[dict[str, Any]] = []

        try:
            for entry in entries:
                checked_count += 1
                detail: dict[str, Any] = {
                    "ecosystem": entry.ecosystem,
                    "package_name": entry.package_name,
                    "previous_version": entry.last_scanned_version,
                }

                # Rate-limit between consecutive package checks
                if checked_count > 1 and self.request_delay_seconds > 0:
                    await asyncio.sleep(self.request_delay_seconds)

                async with sem:
                    has_update, latest_ver = await check_package_update(
                        client=client,
                        ecosystem=entry.ecosystem,
                        package_name=entry.package_name,
                        current_version=entry.last_scanned_version,
                    )

                entry.last_checked_at = datetime.now(UTC)
                if latest_ver:
                    entry.latest_version = latest_ver
                entry.has_update = has_update

                detail["latest_version"] = latest_ver
                detail["has_update"] = has_update
                detail["scan_triggered"] = False

                if has_update and latest_ver:
                    updates_detected += 1
                    if auto_scan:
                        # Prevent duplicate scans if already queued, running, or completed
                        existing_scan = (
                            session.query(models.Scan)
                            .filter(
                                models.Scan.ecosystem == entry.ecosystem,
                                models.Scan.package_name == entry.package_name,
                                models.Scan.version == latest_ver,
                                models.Scan.status.in_(
                                    [
                                        ScanState.ACCEPTED.value,
                                        ScanState.RUNNING.value,
                                        ScanState.COMPLETED.value,
                                    ]
                                ),
                            )
                            .first()
                        )
                        if existing_scan:
                            detail["scan_id"] = str(existing_scan.id)
                            detail["duplicate_skipped"] = True
                        else:
                            try:
                                scan_req = ScanRequest(
                                    ecosystem=Ecosystem(entry.ecosystem),
                                    package_name=entry.package_name,
                                    version=latest_ver,
                                )
                                scan_res = await scan_manager.create_scan(scan_req)
                                scans_triggered += 1
                                detail["scan_triggered"] = True
                                detail["scan_id"] = str(scan_res.scan_id)
                            except Exception as exc:
                                logger.warning(
                                    "Failed to trigger scan for update %s:%s@%s: %s",
                                    entry.ecosystem,
                                    entry.package_name,
                                    latest_ver,
                                    exc,
                                )

                # Check if we can compute a release comparison
                self._update_comparison_if_possible(repo, entry)
                session.flush()
                details.append(detail)

            session.commit()

        finally:
            if owns_client:
                await client.aclose()

        self._last_check_timestamp = datetime.now(UTC).isoformat()
        self._last_check_results = {
            "checked_count": checked_count,
            "updates_detected": updates_detected,
            "scans_triggered": scans_triggered,
        }

        return WatchlistCheckResponse(
            checked_count=checked_count,
            updates_detected=updates_detected,
            scans_triggered=scans_triggered,
            details=details,
        )

    async def _check_in_memory_watchlist(
        self,
        scan_manager: ScanManager,
        client: httpx.AsyncClient | None,
        auto_scan: bool,
    ) -> WatchlistCheckResponse:
        entries = getattr(scan_manager, "_in_memory_watchlist", {})
        if not entries:
            return WatchlistCheckResponse(
                checked_count=0,
                updates_detected=0,
                scans_triggered=0,
                details=[],
            )

        owns_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            owns_client = True

        sem = asyncio.Semaphore(self.max_concurrency)
        checked_count = 0
        updates_detected = 0
        scans_triggered = 0
        details: list[dict[str, Any]] = []

        try:
            for entry in list(entries.values()):
                checked_count += 1
                eco = str(entry.get("ecosystem", "npm"))
                pkg_name = str(entry.get("package_name", ""))
                prev_ver = entry.get("last_scanned_version")

                detail: dict[str, Any] = {
                    "ecosystem": eco,
                    "package_name": pkg_name,
                    "previous_version": prev_ver,
                }

                if checked_count > 1 and self.request_delay_seconds > 0:
                    await asyncio.sleep(self.request_delay_seconds)

                async with sem:
                    has_update, latest_ver = await check_package_update(
                        client=client,
                        ecosystem=eco,
                        package_name=pkg_name,
                        current_version=prev_ver,
                    )

                entry["last_checked_at"] = datetime.now(UTC).isoformat()
                if latest_ver:
                    entry["latest_version"] = latest_ver
                entry["has_update"] = has_update

                detail["latest_version"] = latest_ver
                detail["has_update"] = has_update
                detail["scan_triggered"] = False

                if has_update and latest_ver:
                    updates_detected += 1
                    if auto_scan:
                        # Prevent duplicate scans in memory
                        existing_mem = next(
                            (
                                s
                                for s in getattr(scan_manager, "_scans", {}).values()
                                if s.ecosystem == eco
                                and s.package_name == pkg_name
                                and s.version == latest_ver
                                and s.status
                                in (
                                    ScanState.ACCEPTED,
                                    ScanState.RUNNING,
                                    ScanState.COMPLETED,
                                )
                            ),
                            None,
                        )
                        if existing_mem:
                            detail["scan_id"] = str(existing_mem.scan_id)
                            detail["duplicate_skipped"] = True
                        else:
                            try:
                                scan_req = ScanRequest(
                                    ecosystem=Ecosystem(eco),
                                    package_name=pkg_name,
                                    version=latest_ver,
                                )
                                scan_res = await scan_manager.create_scan(scan_req)
                                scans_triggered += 1
                                detail["scan_triggered"] = True
                                detail["scan_id"] = str(scan_res.scan_id)
                            except Exception as exc:
                                logger.warning(
                                    "Failed to trigger in-memory scan for update %s:%s@%s: %s",
                                    eco,
                                    pkg_name,
                                    latest_ver,
                                    exc,
                                )

                self._update_in_memory_comparison(scan_manager, entry)
                details.append(detail)

        finally:
            if owns_client:
                await client.aclose()

        self._last_check_timestamp = datetime.now(UTC).isoformat()
        self._last_check_results = {
            "checked_count": checked_count,
            "updates_detected": updates_detected,
            "scans_triggered": scans_triggered,
        }

        return WatchlistCheckResponse(
            checked_count=checked_count,
            updates_detected=updates_detected,
            scans_triggered=scans_triggered,
            details=details,
        )

    def _update_in_memory_comparison(
        self,
        scan_manager: ScanManager,
        entry: dict[str, Any],
    ) -> None:
        """Compute and store release comparison in in-memory watchlist entry if reports exist."""
        try:
            head_ver = entry.get("latest_version")
            base_ver = entry.get("last_scanned_version")
            if not head_ver or not base_ver or head_ver == base_ver:
                return

            eco = entry.get("ecosystem")
            pkg_name = entry.get("package_name")

            scans = list(getattr(scan_manager, "_scans", {}).values())
            head_scan = next(
                (
                    s
                    for s in scans
                    if s.ecosystem == eco
                    and s.package_name == pkg_name
                    and s.version == head_ver
                    and s.status == ScanState.COMPLETED
                    and s.report is not None
                ),
                None,
            )
            base_scan = next(
                (
                    s
                    for s in scans
                    if s.ecosystem == eco
                    and s.package_name == pkg_name
                    and s.version == base_ver
                    and s.status == ScanState.COMPLETED
                    and s.report is not None
                ),
                None,
            )

            if head_scan and head_scan.report:
                comparison = compare_releases(
                    head_scan.report,
                    base_scan.report if base_scan else None,
                )
                entry["diff_summary"] = comparison.model_dump(mode="json")
                if comparison.risk_change.head_score is not None:
                    entry["last_risk_score"] = comparison.risk_change.head_score
                if comparison.risk_change.head_level:
                    entry["last_risk_level"] = comparison.risk_change.head_level
        except Exception as exc:
            logger.debug(
                "Could not compute in-memory release comparison for %s: %s",
                entry.get("id"),
                exc,
            )

    def _update_comparison_if_possible(
        self,
        repo: ScanRepository,
        entry: models.WatchlistEntry,
    ) -> None:
        """If versions both have reports, compute and cache release comparison."""
        try:
            if not entry.last_scanned_version or not entry.latest_version:
                return
            if entry.last_scanned_version == entry.latest_version:
                return

            pkg = repo.get_or_create_package(entry.ecosystem, entry.package_name)
            v_base = repo.get_or_create_version(pkg.id, entry.last_scanned_version)
            v_head = repo.get_or_create_version(pkg.id, entry.latest_version)

            # Find latest completed scan for head and base
            head_scan = (
                repo.session.query(models.Scan)
                .filter(
                    models.Scan.package_version_id == v_head.id,
                    models.Scan.status == ScanState.COMPLETED.value,
                )
                .order_by(models.Scan.created_at.desc())
                .first()
            )
            base_scan = (
                repo.session.query(models.Scan)
                .filter(
                    models.Scan.package_version_id == v_base.id,
                    models.Scan.status == ScanState.COMPLETED.value,
                )
                .order_by(models.Scan.created_at.desc())
                .first()
            )

            if head_scan:
                head_rep = repo.get_report(head_scan.id)
                base_rep = repo.get_report(base_scan.id) if base_scan else None
                if head_rep:
                    comparison = compare_releases(head_rep, base_rep)
                    entry.diff_summary_json = comparison.model_dump(mode="json")
                    if comparison.risk_change.head_score is not None:
                        entry.last_risk_score = comparison.risk_change.head_score
                    if comparison.risk_change.head_level:
                        entry.last_risk_level = comparison.risk_change.head_level
        except Exception as exc:
            logger.debug("Could not compute release comparison for %s: %s", entry.id, exc)

    async def start(
        self,
        session_factory: Any,
        scan_manager: ScanManager,
    ) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    if session_factory:
                        with session_factory() as session:
                            await self.check_watchlist_now(session, scan_manager)
                    else:
                        await self.check_watchlist_now(None, scan_manager)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Error in release monitoring background check: %s", exc)

                try:
                    await asyncio.sleep(self.interval_seconds)
                except asyncio.CancelledError:
                    break

        self._task = asyncio.create_task(_loop())

    def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


# Global scheduler instance
_global_scheduler = ReleaseMonitoringScheduler()


def get_monitoring_scheduler() -> ReleaseMonitoringScheduler:
    return _global_scheduler
