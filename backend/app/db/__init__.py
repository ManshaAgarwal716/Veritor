"""Database models and persistence layer."""

from app.db.base import Base
from app.db.models import (
    AIExplanation,
    FileComparison,
    Package,
    PackageVersion,
    ProvenanceResultModel,
    Scan,
    ScanReport,
    SecurityFinding,
    WatchlistEntry,
)
from app.db.repository import ScanRepository
from app.db.session import get_db_session, get_engine, get_session_factory, init_db

__all__ = [
    "AIExplanation",
    "Base",
    "FileComparison",
    "Package",
    "PackageVersion",
    "ProvenanceResultModel",
    "Scan",
    "ScanReport",
    "ScanRepository",
    "SecurityFinding",
    "WatchlistEntry",
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "init_db",
]
