# Veritor REST API Reference

The Veritor API is built with FastAPI. Interactive Swagger UI is available at `http://localhost:8000/docs` and OpenAPI JSON schema at `http://localhost:8000/openapi.json`.

All endpoints are versioned under the `/api/v1` prefix, except `/health`.

---

## 1. System Health

### `GET /health`
Check backend server readiness.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

## 2. Package Scans (`/api/v1/scans`)

### `POST /api/v1/scans`
Submit a package and exact version for analysis. Returns immediately with `202 Accepted` while analysis executes asynchronously.

**Request Body:**
```json
{
  "ecosystem": "npm",
  "package_name": "chalk",
  "version": "5.3.0"
}
```

*Supported ecosystems: `npm`, `pypi`.*

**Response (202 Accepted):**
```json
{
  "scan_id": "a3b84b55-d36c-4824-a744-8cb38a065cb9",
  "ecosystem": "npm",
  "package_name": "chalk",
  "version": "5.3.0",
  "status": "accepted",
  "stage": "queued",
  "progress_percent": 0,
  "message": "Scan accepted and queued for processing",
  "created_at": "2026-11-01T14:00:00Z"
}
```

---

### `GET /api/v1/scans/{scan_id}`
Retrieve the real-time status and stage progress of an active or completed scan.

**Response (200 OK):**
```json
{
  "scan_id": "a3b84b55-d36c-4824-a744-8cb38a065cb9",
  "ecosystem": "npm",
  "package_name": "chalk",
  "version": "5.3.0",
  "status": "completed",
  "stage": "completed",
  "progress_percent": 100,
  "message": "Analysis completed successfully",
  "created_at": "2026-11-01T14:00:00Z",
  "completed_at": "2026-11-01T14:00:04Z",
  "duration_seconds": 4.12
}
```

*Stages: `queued`, `fetching_metadata`, `resolving_source`, `downloading_artifact`, `extracting_package`, `downloading_source`, `extracting_source`, `comparing`, `security_scanning`, `checking_provenance`, `scoring_risk`, `ai_investigation`, `completed`, `failed`.*

---

### `GET /api/v1/scans/{scan_id}/report`
Retrieve the full integrity analysis report. Returns `409 Conflict` if scan is still in progress.

**Response (200 OK):**
```json
{
  "scan_id": "a3b84b55-d36c-4824-a744-8cb38a065cb9",
  "ecosystem": "npm",
  "package_name": "chalk",
  "version": "5.3.0",
  "status": "completed",
  "metadata": { ... },
  "source_match": {
    "status": "MATCHED",
    "repository": { "owner": "chalk", "name": "chalk" },
    "commit_sha": "d2e6f4...",
    "method": "package_tag",
    "confidence": "HIGH"
  },
  "comparison": {
    "total_files": 12,
    "identical_count": 10,
    "added_count": 2,
    "modified_count": 0,
    "removed_count": 0
  },
  "security": {
    "findings": [],
    "files_scanned": 2
  },
  "provenance": {
    "status": "VERIFIED",
    "build_type": "https://actions.github.com/buildtypes/runner/v1",
    "signer_identity": "https://github.com/chalk/chalk/.github/workflows/release.yml@refs/heads/main"
  },
  "risk": {
    "score": 0,
    "level": "LOW",
    "confidence": "HIGH",
    "contributing_evidence": []
  },
  "ai": {
    "status": "completed",
    "model": "qwen2.5-coder:7b",
    "summary": "Package matches source repository and no deterministic security findings were detected."
  }
}
```

---

### `GET /api/v1/scans/{scan_id}/files`
Get the file inventory with source comparison classifications (`IDENTICAL`, `ADDED`, `MODIFIED`, `REMOVED`) and artifact classifications (`SOURCE_AUTHENTIC`, `LIKELY_GENERATED`, `SUSPICIOUS`, `UNCERTAIN`).

---

### `GET /api/v1/scans/{scan_id}/files/{file_id}/diff`
Get the unified text diff for a specific file by its relative path or numeric index.

---

### `GET /api/v1/scans/{scan_id}/findings`
Get security findings identified by the static Tree-Sitter AST scanner and AI investigator explanations.

---

### `GET /api/v1/scans/{scan_id}/export/json`
Download the full package integrity report as a structured JSON file attachment. Includes `export_metadata` with a SHA-256 integrity hash.

---

### `GET /api/v1/scans/{scan_id}/export/pdf`
Download the formatted executive report as a styled PDF document attachment.

---

### `GET /api/v1/scans/{scan_id}/compare-previous`
Compare the scan report against the immediately preceding analyzed version of the same package.

**Response (200 OK):**
```json
{
  "ecosystem": "npm",
  "package_name": "chalk",
  "base_version": "5.2.0",
  "head_version": "5.3.0",
  "base_scan_id": "...",
  "head_scan_id": "...",
  "risk_change": {
    "base_score": 0,
    "head_score": 0,
    "score_delta": 0,
    "is_elevated": false
  },
  "file_changes": {
    "newly_added": ["source.js"],
    "newly_modified": [],
    "newly_removed": [],
    "new_suspicious_artifacts": []
  },
  "finding_changes": {
    "new_findings": [],
    "resolved_findings": [],
    "persistent_count": 0
  },
  "provenance_change": {
    "base_status": "VERIFIED",
    "head_status": "VERIFIED",
    "is_downgraded": false
  },
  "summary": "Release comparison for chalk (5.2.0 → 5.3.0): Risk score remained unchanged at 0 (LOW)."
}
```

---

### `GET /api/v1/scans/compare`
Arbitrary two-scan release comparison.

**Query Parameters:**
- `head_scan_id` (UUID, required): The newer scan.
- `base_scan_id` (UUID, optional): The baseline scan. If omitted, uses the previous release of the same package.

---

## 3. Package Watchlist (`/api/v1/watchlist`)

### `GET /api/v1/watchlist`
List all monitored packages with their latest detected release versions, scan history, risk scores, and update statuses.

**Response (200 OK):**
```json
[
  {
    "id": "npm:chalk",
    "ecosystem": "npm",
    "package_name": "chalk",
    "last_scanned_version": "5.2.0",
    "latest_version": "5.3.0",
    "has_update": true,
    "last_risk_score": 0,
    "last_risk_level": "LOW",
    "last_checked_at": "2026-11-01T14:15:00Z",
    "notes": "Terminal styling library"
  }
]
```

---

### `POST /api/v1/watchlist`
Add a package to the monitoring watchlist.

**Request Body:**
```json
{
  "ecosystem": "npm",
  "package_name": "express",
  "notes": "Critical API framework"
}
```

---

### `DELETE /api/v1/watchlist/{entry_id}`
Remove a package from the watchlist (e.g. `npm:express` or `pypi:requests`).

---

### `POST /api/v1/watchlist/check`
Trigger an on-demand check across all watchlisted packages for newly published releases on npm and PyPI.

**Response (200 OK):**
```json
{
  "checked_count": 5,
  "updates_detected": 1,
  "scans_triggered": 1,
  "details": [
    {
      "ecosystem": "npm",
      "package_name": "chalk",
      "current_version": "5.2.0",
      "latest_version": "5.3.0",
      "has_update": true,
      "scan_triggered": true
    }
  ]
}
```

---

### `GET /api/v1/watchlist/monitoring-status`
Get the operational metrics of the background release monitoring scheduler.

**Response (200 OK):**
```json
{
  "is_running": true,
  "interval_seconds": 3600,
  "monitored_packages_count": 5,
  "total_check_cycles": 12,
  "total_updates_found": 3,
  "total_scans_triggered": 3,
  "last_check_completed_at": "2026-11-01T14:00:00Z"
}
```
