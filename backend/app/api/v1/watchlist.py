"""Watchlist API router."""

from fastapi import APIRouter, HTTPException, status

from app.scans.manager import get_scan_manager
from app.schemas.common import ErrorResponse
from app.schemas.watchlist import WatchlistCreateRequest, WatchlistEntryResponse

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
