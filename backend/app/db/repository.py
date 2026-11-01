"""Repository for saving and reloading package integrity verification data."""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.schemas.scans import (
    FileDiffItem,
    ScanReportResponse,
)

logger = logging.getLogger(__name__)


class ScanRepository:
    """Encapsulates database operations for scans, packages, reports, and findings."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_package(self, ecosystem: str, name: str) -> models.Package:
        """Find or create a package record."""
        stmt = select(models.Package).where(
            models.Package.ecosystem == ecosystem,
            models.Package.name == name,
        )
        pkg = self.session.scalars(stmt).first()
        if not pkg:
            pkg = models.Package(ecosystem=ecosystem, name=name)
            self.session.add(pkg)
            self.session.flush()
        return pkg

    def get_or_create_version(
        self,
        package_id: int,
        version: str,
        published_at: Any = None,
        manifest: dict[str, Any] | None = None,
        source_repo_url: str | None = None,
        source_commit: str | None = None,
    ) -> models.PackageVersion:
        """Find or create a package version record."""
        stmt = select(models.PackageVersion).where(
            models.PackageVersion.package_id == package_id,
            models.PackageVersion.version == version,
        )
        ver = self.session.scalars(stmt).first()
        if not ver:
            ver = models.PackageVersion(
                package_id=package_id,
                version=version,
                published_at=published_at,
                manifest=manifest,
                source_repo_url=source_repo_url,
                source_commit=source_commit,
            )
            self.session.add(ver)
            self.session.flush()
        elif manifest and not ver.manifest:
            ver.manifest = manifest
            if source_repo_url:
                ver.source_repo_url = source_repo_url
            if source_commit:
                ver.source_commit = source_commit
            self.session.flush()
        return ver

    def save_scan(
        self,
        scan_id: uuid.UUID,
        ecosystem: str,
        package_name: str,
        version: str,
        status: str,
        stage: str,
        progress_percent: int,
        message: str,
        created_at: Any,
        started_at: Any = None,
        completed_at: Any = None,
        error: str | None = None,
        duration_seconds: float | None = None,
    ) -> models.Scan:
        """Create or update a scan record."""
        stmt = select(models.Scan).where(models.Scan.id == scan_id)
        scan = self.session.scalars(stmt).first()

        pkg = self.get_or_create_package(ecosystem, package_name)
        ver = self.get_or_create_version(pkg.id, version)

        if not scan:
            scan = models.Scan(
                id=scan_id,
                package_version_id=ver.id,
                ecosystem=ecosystem,
                package_name=package_name,
                version=version,
                status=status,
                stage=stage,
                progress_percent=progress_percent,
                message=message,
                created_at=created_at,
                started_at=started_at,
                completed_at=completed_at,
                error=error,
                duration_seconds=duration_seconds,
            )
            self.session.add(scan)
        else:
            scan.status = status
            scan.stage = stage
            scan.progress_percent = progress_percent
            scan.message = message
            scan.started_at = started_at or scan.started_at
            scan.completed_at = completed_at or scan.completed_at
            scan.error = error or scan.error
            scan.duration_seconds = duration_seconds or scan.duration_seconds

        self.session.flush()
        return scan

    def get_scan(self, scan_id: uuid.UUID) -> models.Scan | None:
        """Retrieve a scan record by ID."""
        stmt = select(models.Scan).where(models.Scan.id == scan_id)
        return self.session.scalars(stmt).first()

    def save_report(
        self,
        scan_id: uuid.UUID,
        report_response: ScanReportResponse,
    ) -> models.ScanReport:
        """Save the complete scan report and associated entities."""
        report_dict = report_response.model_dump(mode="json")
        risk_score = None
        risk_level = None
        confidence = None
        completeness = None

        if report_response.risk:
            risk_dict = (
                report_response.risk
                if isinstance(report_response.risk, dict)
                else report_response.risk.model_dump(mode="json")
            )
            risk_score = risk_dict.get("score")
            risk_level = risk_dict.get("level")
            confidence = risk_dict.get("confidence")
            completeness = risk_dict.get("completeness")

        metadata_json = None
        if isinstance(report_response.metadata, dict):
            metadata_json = report_response.metadata
        elif hasattr(report_response.metadata, "model_dump"):
            metadata_json = report_response.metadata.model_dump(mode="json")  # type: ignore[union-attr]

        source_match_json = None
        if isinstance(report_response.source_match, dict):
            source_match_json = report_response.source_match
        elif hasattr(report_response.source_match, "model_dump"):
            source_match_json = report_response.source_match.model_dump(mode="json")  # type: ignore[union-attr]

        stmt = select(models.ScanReport).where(models.ScanReport.scan_id == scan_id)
        report_model = self.session.scalars(stmt).first()
        if not report_model:
            report_model = models.ScanReport(
                scan_id=scan_id,
                risk_score=risk_score,
                risk_level=risk_level,
                confidence=confidence,
                completeness=completeness,
                metadata_json=metadata_json,
                source_match_json=source_match_json,
                report_json=report_dict,
            )
            self.session.add(report_model)
        else:
            report_model.risk_score = risk_score
            report_model.risk_level = risk_level
            report_model.confidence = confidence
            report_model.completeness = completeness
            report_model.metadata_json = metadata_json
            report_model.source_match_json = source_match_json
            report_model.report_json = report_dict

        # Save file comparisons
        if report_response.comparison:
            files = (
                report_response.comparison.get("files", [])
                if isinstance(report_response.comparison, dict)
                else getattr(report_response.comparison, "files", [])
            )
            for f in files:
                f_dict = f if isinstance(f, dict) else f.model_dump(mode="json")
                fc = models.FileComparison(
                    scan_id=scan_id,
                    path=f_dict.get("path", ""),
                    status=f_dict.get("status", ""),
                    diff_status=f_dict.get("diff_status", "CLEAN"),
                    classification=f_dict.get("classification"),
                    explanation=f_dict.get("explanation"),
                    added_lines=f_dict.get("added_lines"),
                    removed_lines=f_dict.get("removed_lines"),
                    unified_diff=f_dict.get("unified"),
                )
                self.session.add(fc)

        # Save security findings
        if report_response.security:
            findings = (
                report_response.security.get("findings", [])
                if isinstance(report_response.security, dict)
                else getattr(report_response.security, "findings", [])
            )
            for sf in findings:
                sf_dict = sf if isinstance(sf, dict) else sf.model_dump(mode="json")
                f_model = models.SecurityFinding(
                    scan_id=scan_id,
                    rule_id=sf_dict.get("rule_id", ""),
                    path=sf_dict.get("path", ""),
                    line=sf_dict.get("line", 0),
                    severity=sf_dict.get("severity", "INFO"),
                    confidence=str(sf_dict.get("confidence", "HIGH")),
                    evidence=sf_dict.get("evidence", ""),
                    explanation=sf_dict.get("explanation", ""),
                    recommended_action=sf_dict.get("recommended_action", ""),
                )
                self.session.add(f_model)

        # Save provenance
        if report_response.provenance:
            prov_dict = (
                report_response.provenance
                if isinstance(report_response.provenance, dict)
                else report_response.provenance.model_dump(mode="json")
            )
            prov_model = models.ProvenanceResultModel(
                scan_id=scan_id,
                status=prov_dict.get("status", "UNAVAILABLE"),
                sigstore_verified=bool(prov_dict.get("sigstore_verified", False)),
                build_signer=prov_dict.get("build_signer"),
                build_runner=prov_dict.get("build_runner"),
                commit_matched=bool(prov_dict.get("commit_matched", False)),
                repository_matched=bool(prov_dict.get("repository_matched", False)),
                reasons=prov_dict.get("reasons"),
                claims=prov_dict.get("claims"),
            )
            self.session.add(prov_model)

        # Save AI explanations
        if report_response.ai:
            explanations = (
                report_response.ai.get("explanations", [])
                if isinstance(report_response.ai, dict)
                else getattr(report_response.ai, "explanations", [])
            )
            if explanations:
                for exp in explanations:
                    exp_dict = exp if isinstance(exp, dict) else exp.model_dump(mode="json")
                    ai_model = models.AIExplanation(
                        scan_id=scan_id,
                        finding_rule_id=exp_dict.get("finding_rule_id"),
                        file_path=exp_dict.get("file_path"),
                        assessment=exp_dict.get("assessment", ""),
                        reason=exp_dict.get("reason", ""),
                        false_positive_likelihood=exp_dict.get("false_positive_likelihood"),
                    )
                    self.session.add(ai_model)

        self.session.flush()
        return report_model

    def get_report(self, scan_id: uuid.UUID) -> ScanReportResponse | None:
        """Retrieve full scan report."""
        stmt = select(models.ScanReport).where(models.ScanReport.scan_id == scan_id)
        report_model = self.session.scalars(stmt).first()
        if not report_model or not report_model.report_json:
            return None
        try:
            return ScanReportResponse.model_validate(report_model.report_json)
        except Exception as exc:
            logger.warning("Failed to validate report_json for scan %s: %s", scan_id, exc)
            return None

    def get_file_comparisons(self, scan_id: uuid.UUID) -> list[models.FileComparison]:
        stmt = select(models.FileComparison).where(models.FileComparison.scan_id == scan_id)
        return list(self.session.scalars(stmt).all())

    def get_file_diff(self, scan_id: uuid.UUID, path: str) -> FileDiffItem | None:
        stmt = select(models.FileComparison).where(
            models.FileComparison.scan_id == scan_id,
            models.FileComparison.path == path,
        )
        fc = self.session.scalars(stmt).first()
        if not fc:
            return None
        return FileDiffItem(
            path=fc.path,
            status=fc.status,
            diff_status=fc.diff_status,
            unified=fc.unified_diff,
            added_lines=fc.added_lines,
            removed_lines=fc.removed_lines,
        )

    # Watchlist operations
    def get_watchlist(self) -> list[models.WatchlistEntry]:
        stmt = select(models.WatchlistEntry).order_by(models.WatchlistEntry.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def add_watchlist_entry(
        self,
        ecosystem: str,
        package_name: str,
        notes: str | None = None,
    ) -> models.WatchlistEntry:
        entry_id = f"{ecosystem}:{package_name}"
        stmt = select(models.WatchlistEntry).where(models.WatchlistEntry.id == entry_id)
        entry = self.session.scalars(stmt).first()
        if not entry:
            entry = models.WatchlistEntry(
                id=entry_id,
                ecosystem=ecosystem,
                package_name=package_name,
                notes=notes,
            )
            self.session.add(entry)
        else:
            if notes is not None:
                entry.notes = notes
        self.session.flush()
        return entry

    def remove_watchlist_entry(self, entry_id: str) -> bool:
        stmt = select(models.WatchlistEntry).where(models.WatchlistEntry.id == entry_id)
        entry = self.session.scalars(stmt).first()
        if entry:
            self.session.delete(entry)
            self.session.flush()
            return True
        return False
