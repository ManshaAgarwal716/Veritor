"""Watchlist and release monitoring API router."""

from fastapi import APIRouter, HTTPException, status

from app.monitoring.scheduler import get_monitoring_scheduler
from app.scans.manager import get_scan_manager
from app.schemas.common import ErrorResponse
from app.schemas.scans import ReleaseComparisonResponse
from app.schemas.watchlist import (
    MonitoringStatusResponse,
    WatchlistCheckResponse,
    WatchlistCreateRequest,
    WatchlistEntryResponse,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistEntryResponse])
def get_watchlist() -> list[WatchlistEntryResponse]:
    """Retrieve all monitored watchlist packages."""
    entries = get_scan_manager().get_watchlist()
    return [WatchlistEntryResponse.model_validate(e) for e in entries]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WatchlistEntryResponse,
    responses={422: {"model": ErrorResponse}},
)
def add_to_watchlist(request: WatchlistCreateRequest) -> WatchlistEntryResponse:
    """Add a package to the watchlist."""
    item = get_scan_manager().add_watchlist_entry(
        ecosystem=request.ecosystem.value,
        package_name=request.package_name,
        notes=request.notes,
    )
    return WatchlistEntryResponse.model_validate(item)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def remove_from_watchlist(entry_id: str) -> None:
    """Remove a package from the watchlist."""
    removed = get_scan_manager().remove_watchlist_entry(entry_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist entry {entry_id!r} not found",
        )


@router.post(
    "/check",
    response_model=WatchlistCheckResponse,
    status_code=status.HTTP_200_OK,
)
async def check_watchlist_updates() -> WatchlistCheckResponse:
    """Trigger an on-demand check for newly published versions across all watchlisted packages."""
    scan_mgr = get_scan_manager()
    session_factory = getattr(scan_mgr, "_session_factory", None)
    scheduler = get_monitoring_scheduler()

    if session_factory:
        with session_factory() as session:
            return await scheduler.check_watchlist_now(
                session=session,
                scan_manager=scan_mgr,
            )

    return WatchlistCheckResponse(
        checked_count=0,
        updates_detected=0,
        scans_triggered=0,
        details=[],
    )


@router.get(
    "/monitoring-status",
    response_model=MonitoringStatusResponse,
)
def get_monitoring_status() -> MonitoringStatusResponse:
    """Get the current state and metrics of the background release monitor."""
    scan_mgr = get_scan_manager()
    entries = scan_mgr.get_watchlist()
    scheduler = get_monitoring_scheduler()
    return scheduler.get_status(total_monitored=len(entries))


@router.get(
    "/{entry_id}/compare",
    response_model=ReleaseComparisonResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_watchlist_release_comparison(entry_id: str) -> ReleaseComparisonResponse:
    """Get release-to-release comparison for a watchlisted package."""
    scan_mgr = get_scan_manager()
    entries = scan_mgr.get_watchlist()
    target = next((e for e in entries if e["id"] == entry_id), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist entry {entry_id!r} not found",
        )

    diff_summary = target.get("diff_summary")
    if not diff_summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No release comparison available yet for {entry_id!r}. Run a check or scan first."
            ),
        )

    return ReleaseComparisonResponse.model_validate(diff_summary)
