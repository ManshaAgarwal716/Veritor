"""Watchlist request and response schemas."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.scans import Ecosystem


class WatchlistCreateRequest(BaseModel):
    ecosystem: Ecosystem
    package_name: str = Field(min_length=1, max_length=256)
    notes: str | None = None
    auto_scan: bool = True


class WatchlistEntryResponse(BaseModel):
    id: str
    ecosystem: str
    package_name: str
    notes: str | None = None
    last_scanned_version: str | None = None
    last_risk_score: int | None = None
    last_risk_level: str | None = None
    latest_version: str | None = None
    has_update: bool = False
    last_checked_at: str | None = None
    diff_summary: dict[str, Any] | None = None
    created_at: str | None = None


class WatchlistCheckResponse(BaseModel):
    checked_count: int
    updates_detected: int
    scans_triggered: int
    details: list[dict[str, Any]] = []


class MonitoringStatusResponse(BaseModel):
    is_running: bool
    interval_seconds: int
    monitored_packages_count: int
    last_check_timestamp: str | None = None
    last_check_results: dict[str, Any] | None = None
