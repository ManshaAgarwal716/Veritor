"""Structured JSON export generator for package integrity reports."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.schemas.scans import ScanReportResponse


def _to_serializable(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    if isinstance(val, (list, tuple)):
        return [_to_serializable(x) for x in val]
    if isinstance(val, dict):
        return {k: _to_serializable(v) for k, v in val.items()}
    if hasattr(val, "model_dump"):
        return val.model_dump(mode="json")
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def generate_json_report(report: ScanReportResponse) -> dict[str, Any]:
    """Generate a comprehensive, standardized, export-ready JSON report."""
    metadata = _to_serializable(report.metadata) or {}
    source = _to_serializable(report.source_match) or {}
    comparison = _to_serializable(report.comparison) or {}
    security = _to_serializable(report.security) or {}
    provenance = _to_serializable(report.provenance) or {}
    risk = _to_serializable(report.risk) or {}
    ai = _to_serializable(report.ai) or {}

    # Extract comparison summary stats
    files = comparison.get("files", [])
    total_files = len(files)
    identical = sum(1 for f in files if f.get("status") == "IDENTICAL")
    added = sum(1 for f in files if f.get("status") == "ADDED")
    modified = sum(1 for f in files if f.get("status") == "MODIFIED")
    removed = sum(1 for f in files if f.get("status") == "REMOVED")
    suspicious = sum(1 for f in files if str(f.get("classification") or "").upper() == "SUSPICIOUS")
    generated = sum(
        1 for f in files if str(f.get("classification") or "").upper() == "LIKELY_GENERATED"
    )
    uncertain = sum(1 for f in files if str(f.get("classification") or "").upper() == "UNCERTAIN")

    comparison_stats = {
        "total_files": comparison.get("total_files", total_files),
        "identical_files_count": identical,
        "added_files_count": added,
        "modified_files_count": modified,
        "removed_files_count": removed,
        "likely_generated_count": generated,
        "suspicious_artifacts_count": suspicious,
        "uncertain_artifacts_count": uncertain,
    }

    # Extract risk summary
    factors = risk.get("factors") or risk.get("contributing_factors") or []
    contributing_evidence = risk.get("contributing_evidence") or []
    risk_summary = {
        "score": risk.get("score"),
        "level": risk.get("level"),
        "confidence": risk.get("confidence"),
        "completeness": risk.get("completeness"),
        "summary": risk.get("summary"),
        "factors": factors,
        "contributing_factors": factors,
        "contributing_evidence": contributing_evidence,
        "recommendations": risk.get("recommendations", []),
        "limitations": risk.get("limitations", []),
    }

    # Assemble complete payload
    export_payload: dict[str, Any] = {
        "export_metadata": {
            "schema_version": "1.0.0",
            "generator": "Veritor Package Integrity Analyzer",
            "exported_at": datetime.now(UTC).isoformat(),
        },
        "scan_overview": {
            "scan_id": str(report.scan_id),
            "ecosystem": str(report.ecosystem),
            "package_name": report.package_name,
            "version": report.version,
            "status": str(report.status),
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            "duration_seconds": report.duration_seconds,
        },
        "package_metadata": metadata,
        "source_repository": source,
        "comparison_statistics": comparison_stats,
        "file_comparisons": files,
        "security_findings": security.get("findings", []),
        "provenance_verification": provenance,
        "deterministic_risk_assessment": risk_summary,
        "ai_behavioral_investigation": ai,
    }

    # Compute deterministic integrity hash of report contents
    canonical_bytes = json.dumps(export_payload, sort_keys=True).encode("utf-8")
    integrity_hash = hashlib.sha256(canonical_bytes).hexdigest()
    export_payload["export_metadata"]["report_integrity_sha256"] = integrity_hash

    return export_payload
