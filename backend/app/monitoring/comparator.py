"""Compare two releases of the same package to highlight differences and risk changes."""

import logging
from typing import Any, cast
from uuid import UUID

from app.schemas.scans import (
    Ecosystem,
    FileChangesSummary,
    FindingChangesSummary,
    ProvenanceChangeSummary,
    ReleaseComparisonResponse,
    RiskChangeSummary,
    ScanReportResponse,
)

logger = logging.getLogger(__name__)


def _extract_dict(val: Any) -> dict[str, Any]:
    if not val:
        return {}
    if isinstance(val, dict):
        return cast(dict[str, Any], val)
    if hasattr(val, "model_dump"):
        dumped = val.model_dump(mode="json")
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
    return {}


def compare_releases(
    head_report: ScanReportResponse,
    base_report: ScanReportResponse | None,
) -> ReleaseComparisonResponse:
    """Compare a new release (head) against a previous release (base)."""
    ecosystem = head_report.ecosystem
    package_name = head_report.package_name
    head_version = head_report.version
    head_scan_id = head_report.scan_id

    # If no baseline report exists, head is compared against empty state
    base_version = base_report.version if base_report else "none"
    base_scan_id: UUID | None = base_report.scan_id if base_report else None

    # 1. Risk Changes
    head_risk = _extract_dict(head_report.risk)
    head_score = head_risk.get("score")
    head_level = str(head_risk.get("level") or "UNKNOWN")

    if base_report:
        base_risk = _extract_dict(base_report.risk)
        base_score = base_risk.get("score")
        base_level = str(base_risk.get("level") or "UNKNOWN")
    else:
        base_score = None
        base_level = None

    if head_score is not None and base_score is not None:
        score_delta = head_score - base_score
        is_elevated = head_score > base_score
    else:
        score_delta = 0
        is_elevated = (head_score or 0) > 30

    risk_change = RiskChangeSummary(
        base_score=base_score,
        head_score=head_score,
        score_delta=score_delta,
        base_level=base_level,
        head_level=head_level,
        is_elevated=is_elevated,
    )

    # 2. File Inventory Changes
    head_comp = _extract_dict(head_report.comparison)
    head_files_raw = head_comp.get("files", [])
    head_files = {
        (f if isinstance(f, dict) else f.model_dump()).get("path", ""): (
            f if isinstance(f, dict) else f.model_dump()
        )
        for f in head_files_raw
        if (f if isinstance(f, dict) else f.model_dump()).get("path")
    }

    base_files: dict[str, dict[str, Any]] = {}
    if base_report:
        base_comp = _extract_dict(base_report.comparison)
        base_files_raw = base_comp.get("files", [])
        base_files = {
            (f if isinstance(f, dict) else f.model_dump()).get("path", ""): (
                f if isinstance(f, dict) else f.model_dump()
            )
            for f in base_files_raw
            if (f if isinstance(f, dict) else f.model_dump()).get("path")
        }

    head_paths = set(head_files.keys())
    base_paths = set(base_files.keys())

    newly_added = sorted(head_paths - base_paths)
    newly_removed = sorted(base_paths - head_paths)
    common_paths = head_paths & base_paths

    newly_modified: list[str] = []
    for path in sorted(common_paths):
        h_f = head_files[path]
        b_f = base_files[path]
        if (
            h_f.get("unified") != b_f.get("unified")
            or h_f.get("diff_status") != b_f.get("diff_status")
            or h_f.get("status") != b_f.get("status")
        ):
            newly_modified.append(path)

    new_suspicious_artifacts: list[str] = []
    for path, f in head_files.items():
        classification = str(f.get("classification") or "")
        if classification.upper() == "SUSPICIOUS":
            # Was not suspicious in base
            base_cls = str(base_files.get(path, {}).get("classification") or "")
            if base_cls.upper() != "SUSPICIOUS":
                new_suspicious_artifacts.append(path)

    file_changes = FileChangesSummary(
        newly_added=newly_added,
        newly_removed=newly_removed,
        newly_modified=newly_modified,
        new_suspicious_artifacts=new_suspicious_artifacts,
    )

    # 3. Security Finding Changes
    head_sec = _extract_dict(head_report.security)
    head_findings_raw = head_sec.get("findings", [])
    head_findings = [f if isinstance(f, dict) else f.model_dump() for f in head_findings_raw]

    base_findings: list[dict[str, Any]] = []
    if base_report:
        base_sec = _extract_dict(base_report.security)
        base_findings_raw = base_sec.get("findings", [])
        base_findings = [f if isinstance(f, dict) else f.model_dump() for f in base_findings_raw]

    base_finding_keys = {(f.get("rule_id"), f.get("path"), f.get("line")) for f in base_findings}
    head_finding_keys = {(f.get("rule_id"), f.get("path"), f.get("line")) for f in head_findings}

    new_findings = [
        f
        for f in head_findings
        if (f.get("rule_id"), f.get("path"), f.get("line")) not in base_finding_keys
    ]
    resolved_findings = [
        f
        for f in base_findings
        if (f.get("rule_id"), f.get("path"), f.get("line")) not in head_finding_keys
    ]
    persistent_count = len(base_finding_keys & head_finding_keys)

    finding_changes = FindingChangesSummary(
        new_findings=new_findings,
        resolved_findings=resolved_findings,
        persistent_findings_count=persistent_count,
    )

    # 4. Provenance Changes
    head_prov = _extract_dict(head_report.provenance)
    head_prov_status = head_prov.get("status")

    if base_report:
        base_prov = _extract_dict(base_report.provenance)
        base_prov_status = base_prov.get("status")
    else:
        base_prov_status = None

    is_downgraded = base_prov_status == "VERIFIED" and head_prov_status not in ("VERIFIED", None)

    provenance_change = ProvenanceChangeSummary(
        base_status=base_prov_status,
        head_status=head_prov_status,
        is_downgraded=is_downgraded,
    )

    # 5. Explainable Summary Construction
    parts: list[str] = []
    if base_report:
        parts.append(f"Release comparison for {package_name} ({base_version} → {head_version}):")
        if score_delta != 0:
            direction = "increased" if score_delta > 0 else "decreased"
            parts.append(
                f"Risk score {direction} from {base_score} ({base_level}) "
                f"to {head_score} ({head_level}) [delta: {score_delta:+d}]."
            )
        else:
            parts.append(f"Risk score remained unchanged at {head_score} ({head_level}).")

        if newly_added or newly_modified or newly_removed:
            parts.append(
                f"File changes: +{len(newly_added)} added, ~{len(newly_modified)} modified, "
                f"-{len(newly_removed)} removed."
            )

        if new_suspicious_artifacts:
            art_sample = ", ".join(new_suspicious_artifacts[:3])
            parts.append(
                f"⚠️ {len(new_suspicious_artifacts)} new suspicious artifact(s) "
                f"identified: {art_sample}."
            )

        if new_findings:
            finding_sample = ", ".join(f.get("rule_id", "") for f in new_findings[:3])
            parts.append(
                f"⚠️ {len(new_findings)} newly introduced security finding(s): {finding_sample}."
            )

        if resolved_findings:
            parts.append(f"✅ {len(resolved_findings)} previously reported finding(s) resolved.")

        if is_downgraded:
            parts.append(
                f"⚠️ Provenance verification downgraded from {base_prov_status} to "
                f"{head_prov_status}."
            )
    else:
        parts.append(
            f"Initial analyzed release for {package_name} ({head_version}) "
            f"with risk score {head_score} ({head_level})."
        )
        if head_findings:
            parts.append(f"Contains {len(head_findings)} active security finding(s).")

    summary_text = " ".join(parts)

    return ReleaseComparisonResponse(
        ecosystem=Ecosystem(ecosystem) if isinstance(ecosystem, str) else ecosystem,
        package_name=package_name,
        base_version=base_version,
        head_version=head_version,
        base_scan_id=base_scan_id,
        head_scan_id=head_scan_id,
        risk_change=risk_change,
        file_changes=file_changes,
        finding_changes=finding_changes,
        provenance_change=provenance_change,
        summary=summary_text,
    )
