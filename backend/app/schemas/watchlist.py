"""Watchlist request and response schemas."""

from pydantic import BaseModel, Field

from app.schemas.scans import Ecosystem


class WatchlistCreateRequest(BaseModel):
    ecosystem: Ecosystem
    package_name: str = Field(min_length=1, max_length=256)
    notes: str | None = None


class WatchlistEntryResponse(BaseModel):
    id: str
    ecosystem: str
    package_name: str
    notes: str | None = None
    last_scanned_version: str | None = None
    last_risk_score: int | None = None
    last_risk_level: str | None = None
    created_at: str | None = None
