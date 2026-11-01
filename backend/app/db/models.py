"""SQLAlchemy models for package integrity persistence."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# Use JSONB for PostgreSQL when available, fallback to standard JSON for SQLite
JsonType = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Package(Base):
    """A software package published to a registry (npm or PyPI)."""

    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ecosystem: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list["PackageVersion"]] = relationship(
        "PackageVersion", back_populates="package", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("ecosystem", "name", name="uq_packages_ecosystem_name"),
        Index("ix_packages_ecosystem_name", "ecosystem", "name"),
    )


class PackageVersion(Base):
    """An exact published version of a package."""

    __tablename__ = "package_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(256), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    source_repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    package: Mapped["Package"] = relationship("Package", back_populates="versions")
    scans: Mapped[list["Scan"]] = relationship("Scan", back_populates="package_version")

    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_package_versions_package_version"),
        Index("ix_package_versions_version", "package_id", "version"),
    )


class Scan(Base):
    """An execution of the package integrity verification pipeline."""

    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    package_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("package_versions.id", ondelete="SET NULL"), nullable=True
    )
    ecosystem: Mapped[str] = mapped_column(String(16), nullable=False)
    package_name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="accepted")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    package_version: Mapped["PackageVersion | None"] = relationship(
        "PackageVersion", back_populates="scans"
    )
    report: Mapped["ScanReport | None"] = relationship(
        "ScanReport", back_populates="scan", uselist=False, cascade="all, delete-orphan"
    )
    file_comparisons: Mapped[list["FileComparison"]] = relationship(
        "FileComparison", back_populates="scan", cascade="all, delete-orphan"
    )
    security_findings: Mapped[list["SecurityFinding"]] = relationship(
        "SecurityFinding", back_populates="scan", cascade="all, delete-orphan"
    )
    provenance: Mapped["ProvenanceResultModel | None"] = relationship(
        "ProvenanceResultModel", back_populates="scan", uselist=False, cascade="all, delete-orphan"
    )
    ai_explanations: Mapped[list["AIExplanation"]] = relationship(
        "AIExplanation", back_populates="scan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_scans_pkg_ver", "ecosystem", "package_name", "version"),
        Index("ix_scans_created_at", "created_at"),
    )


class ScanReport(Base):
    """Full serialized integrity report."""

    __tablename__ = "scan_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completeness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    source_match_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    report_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="report")


class FileComparison(Base):
    """Individual file differential analysis result."""

    __tablename__ = "file_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    diff_status: Mapped[str] = mapped_column(String(32), nullable=False, default="CLEAN")
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_lines: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removed_lines: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unified_diff: Mapped[str | None] = mapped_column(Text, nullable=True)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="file_comparisons")

    __table_args__ = (
        Index("ix_file_comparisons_scan_id", "scan_id"),
        Index("ix_file_comparisons_scan_path", "scan_id", "path"),
    )


class SecurityFinding(Base):
    """Static AST security finding."""

    __tablename__ = "security_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), default="HIGH")
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="security_findings")

    __table_args__ = (
        Index("ix_security_findings_scan_id", "scan_id"),
        Index("ix_security_findings_rule_id", "rule_id"),
    )


class ProvenanceResultModel(Base):
    """Sigstore provenance and build origin verification result."""

    __tablename__ = "provenance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sigstore_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    build_signer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_runner: Mapped[str | None] = mapped_column(String(512), nullable=True)
    commit_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    repository_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list[Any] | None] = mapped_column(JsonType, nullable=True)
    claims: Mapped[list[Any] | None] = mapped_column(JsonType, nullable=True)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="provenance")


class AIExplanation(Base):
    """AI investigator reasoning for a specific finding."""

    __tablename__ = "ai_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    finding_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    assessment: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    false_positive_likelihood: Mapped[str | None] = mapped_column(String(32), nullable=True)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="ai_explanations")

    __table_args__ = (Index("ix_ai_explanations_scan_id", "scan_id"),)


class WatchlistEntry(Base):
    """Monitored packages in watchlist."""

    __tablename__ = "watchlist_entries"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ecosystem: Mapped[str] = mapped_column(String(16), nullable=False)
    package_name: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_scanned_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latest_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    has_update: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    diff_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("ecosystem", "package_name", name="uq_watchlist_ecosystem_package"),
        Index("ix_watchlist_ecosystem_package", "ecosystem", "package_name"),
    )
