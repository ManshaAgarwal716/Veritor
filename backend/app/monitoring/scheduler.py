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


class ReleaseMonitoringScheduler:
    """Coordinates periodic checks and rate-limited detection of package releases."""

    def __init__(
        self,
        interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.request_delay_seconds = request_delay_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_check_timestamp: str | None = None
        self._last_check_results: dict[str, Any] | None = None

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
        """Perform a rate-limited check across all monitored watchlist packages."""
        if session is None:
            return WatchlistCheckResponse(
                checked_count=0,
                updates_detected=0,
                scans_triggered=0,
                details=[],
            )

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

                # Rate-limit between requests
                if checked_count > 1 and self.request_delay_seconds > 0:
                    await asyncio.sleep(self.request_delay_seconds)

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
                # If package has latest version report and previous version report
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
