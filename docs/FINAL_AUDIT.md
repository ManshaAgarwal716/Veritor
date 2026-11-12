# Veritor Technical Audit Report

**Date**: 2026-11-02  
**Auditor**: Veritor Core Architecture Team  
**Scope**: Full Stack Inspection (Frontend, Backend, APIs, Adapters, Extraction, Comparison, Artifact Classifier, Security Scanner, Provenance, Risk Engine, AI Investigator, Database, Monitoring, Reports, Docker, CI/CD)  
**Status**: Post-Development Technical Audit  

---

## Executive Summary

Veritor has successfully established a deterministic, evidence-first pipeline for analyzing software supply-chain integrity across npm and PyPI ecosystems. Its core principles—zero untrusted code execution, separation of deterministic static analysis from AI reasoning, and strict provenance verification—are solidly architected and validated by 893 backend tests and passing CI/CD workflows.

This audit evaluates the codebase against the standards of a **serious open-source project**, **production-quality software**, and **research-grade technical portfolio**. 

The audit identified **18 specific findings** across 7 categories:
- **0 Critical Vulnerabilities** (zero remote code execution, zero path traversal escapes).
- **2 High Severity Findings** (missing Python AST security scanning for PyPI; frontend tests lack real component rendering).
- **7 Medium Severity Findings** (diff viewer split mode not rendered, PEP 740 bundle cryptographic verification depth, in-memory watchlist checking, frontend-backend watchlist sync, concurrent stress testing, migration rollback testing, and AI prompt delimitation).
- **9 Low / Informational Findings** (JSON export factor keys, compose healthcheck hardcoding, container `.env` path resolution, URL encoding edge cases, unused function arguments, and sequential polling bottlenecks).

---

## Findings Matrix

| ID | Category | Severity | Affected Component / File | Summary |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Incomplete Feature | **HIGH** | `backend/app/analysis/analyzer.py` | PyPI Python files (`.py`) treated as unsupported language gaps; lacks native Python AST scanner (Status: **FIXED**) |
| **TST-01** | Missing Tests | **HIGH** | `frontend/tests/*.test.mjs` | Frontend tests rely solely on file existence and regex; lacks React component DOM/integration tests (Status: **FIXED**) |
| **INT-01** | Bug / Integration | **MEDIUM** | `frontend/src/app/page.tsx`, `WatchlistView.tsx` | ScannerForm watchlist action only updates `localStorage` without syncing to backend PostgreSQL (Status: **FIXED**) |
| **FEAT-01** | Incomplete Feature | **MEDIUM** | `frontend/src/components/DiffViewer.tsx` | Split/side-by-side diff mode toggle sets state but only unified diff table is implemented (Status: **FIXED**) |
| **FEAT-02** | Incomplete Feature | **MEDIUM** | `backend/app/provenance/pypi.py` | PyPI PEP 740 attestation parses bundle dictionaries but lacks Sigstore cryptographic verification (Status: **FIXED**) |
| **ASSUM-01**| Incorrect Assumption| **MEDIUM** | `backend/app/monitoring/scheduler.py` | Release monitoring check requires DB session; aborts in in-memory mode without checking in-memory watchlist (Status: **FIXED**) |
| **SEC-02** | Security Boundary | **MEDIUM** | `backend/app/ai/investigator.py` | Code diffs and script contents passed to AI prompt lack strict structured enclosure tags |
| **TST-02** | Missing Tests | **MEDIUM** | `backend/tests/test_concurrency_and_stress.py` | Lacks concurrent stress tests evaluating pipeline race conditions and simultaneous scans (Status: **FIXED**) |
| **TST-03** | Missing Tests | **MEDIUM** | `backend/alembic/` | Lacks automated migration tests exercising forward `upgrade head` and reverse `downgrade base` (Status: **FIXED**) |
| **BUG-01** | Bug / Data Parity | **LOW** | `backend/app/reports/json_exporter.py` | JSON exporter queries `contributing_factors` instead of model field `factors` (Status: **FIXED**) |
| **BUG-02** | Docker Config | **LOW** | `docker-compose.yml` | Postgres container healthcheck hardcodes `-U veritor -d veritor` (Status: **FIXED**) |
| **BUG-03** | API Integration | **LOW** | `frontend/src/lib/api.ts` | File diff endpoint interpolates path directly without per-segment URL encoding (Status: **FIXED**) |
| **ASSUM-02**| Incorrect Assumption| **LOW** | `backend/app/config.py` | `REPO_ROOT` path resolution resolves to `/` inside containerized `WORKDIR /app` (Status: **FIXED**) |
| **PERF-01** | Performance | **LOW** | `backend/app/comparison/trees.py` | Repetitive small synchronous file IO reads across archive trees during inventory comparison (Status: **FIXED**) |
| **PERF-02** | Performance | **LOW** | `backend/app/monitoring/scheduler.py` | Watchlist update checks execute sequentially with sleep delay rather than bounded concurrency (Status: **FIXED**) |
| **CODE-01** | Unused Code | **LOW** | `backend/app/ai/investigator.py` | `package_dir: Path | None = None` accepted by `AIInvestigator.investigate` but never read (Status: **FIXED**) |
| **CODE-02** | Code Duplication | **LOW** | `frontend/src/lib/storage.ts` vs `api.ts` | Dual persistence mechanisms for history and watchlist with manual synchronization (Status: **FIXED**) |
| **FEAT-03** | Incomplete Feature | **LOW** | `backend/app/source/` | Source code resolution is restricted to GitHub; GitLab/Bitbucket return `UNSUPPORTED_HOST` (Status: **FIXED**) |

---

## Detailed Audit Findings

### 1. Incomplete Features & Technical Depth

#### SEC-01: Python Code in PyPI Packages Lacks AST Security Scanning
- **Severity**: **HIGH**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/analysis/analyzer.py:38, 74-84`](file:///Users/apple12390/Veritor/backend/app/analysis/analyzer.py#L38-L84)
- **Evidence**:
  ```python
  _OTHER_CODE_SUFFIXES = (".sh", ".bash", ".py", ".ps1", ".bat", ".cmd", ".rb", ".pl")
  ...
  language = scannable_language(target.path) or _script_language(target.entry)
  if language is None:
      if target.path.lower().endswith(_OTHER_CODE_SUFFIXES):
          gaps.append(
              AnalysisGap(
                  path=target.path,
                  reason=GapReason.UNSUPPORTED_LANGUAGE,
                  detail="This code is not JavaScript or TypeScript, so it was not scanned.",
              )
          )
      continue
  ```
- **Analysis**: While Tree-Sitter statically parsed JavaScript and TypeScript (.js, .jsx, .ts, .tsx, .mjs, .cjs), Python `.py` files in PyPI packages were bypassed and recorded as `UNSUPPORTED_LANGUAGE` gaps. PyPI packages benefited from file inventory diffing, manifest verification, and provenance checks, but dynamic code execution (e.g. `eval()`, `exec()`, `os.system()`, `subprocess.Popen`) inside `.py` files was not statically analyzed.
- **Fix Applied**: Implemented a modular, native Python AST security scanner in [`backend/app/analysis/py_scanner.py`](file:///Users/apple12390/Veritor/backend/app/analysis/py_scanner.py) using Python's standard `ast` module. Statically analyzes AST nodes without executing code, matching the exact finding schema and rule catalog (`EXEC-001` through `EXEC-005`, `PROC-001` through `PROC-005`, `ENV-001` through `ENV-003`, `NET-001` through `NET-003`, `FS-001`, `FS-002`, `OBF-001` through `OBF-004`, and `CORR-001` through `CORR-005`). Updated `scannable_language()` and [`backend/app/analysis/analyzer.py`](file:///Users/apple12390/Veritor/backend/app/analysis/analyzer.py) to dispatch `.py` files to `scan_python()` and removed `.py` from `_OTHER_CODE_SUFFIXES`.
- **Test Verification**: Created `backend/tests/test_py_scanner.py` with 19 comprehensive unit tests verifying dynamic execution (`eval`, `exec`, `compile`, `builtins` resolution), process invocation (`subprocess`, `os.system`, `asyncio`), decoded command propagation, environment variable reading, network exfiltration, dynamic imports, filesystem/startup persistence with variable tracking, obfuscation/decompression decoders, extensionless script shebang routing, syntax error resilience, and absence of `UNSUPPORTED_LANGUAGE` gaps for Python code. Verified with `pytest backend/tests` (954 passed).

---

#### FEAT-01: Split / Side-by-Side Diff View Mode Not Implemented (Status: **RESOLVED / FIXED**)
- **Severity**: **MEDIUM**
- **Affected File**: [`frontend/src/components/DiffViewer.tsx`](file:///Users/apple12390/Veritor/frontend/src/components/DiffViewer.tsx)
- **Evidence**:
  ```tsx
  const [viewMode, setViewMode] = useState<"unified" | "split">("unified");
  ...
  <button onClick={() => setViewMode("split")} ...>
  ...
  // Body rendering ignores viewMode:
  <table className="w-full border-collapse">
    <tbody>
      {lines.map((line, idx) => { ... })}
    </tbody>
  </table>
  ```
- **Analysis**: The UI exposes a view mode toggle between "Unified" and "Side-by-side" (split). Clicking "split" updates component state, but the rendered diff view only ever displays a single-column unified diff table. Users cannot view side-by-side source-vs-package differences.
- **Remediation**: Parse unified diff hunks into dual-column rows (`leftLine`, `leftText`, `rightLine`, `rightText`) and render a two-pane split table when `viewMode === "split"`.
- **Fix Applied**: Fully implemented both Unified and Side-by-Side (split) diff modes in [`frontend/src/components/DiffViewer.tsx`](file:///Users/apple12390/Veritor/frontend/src/components/DiffViewer.tsx). Developed `parseUnifiedDiff()` which accurately tracks hunk line numbers (`oldLine` and `newLine`), parses header metadata (`@@ -old,count +new,count @@`), and aligns modified lines side-by-side by pairing deletion and addition batches side-by-side without fabricating missing source lines. Implemented syntax highlighting (`highlightTokens()`) for keywords, strings, comments, numbers, and booleans. Handled binary diffs (`BINARY`), added files missing in source (`ADDED`), removed files (`REMOVED`), identical files (`IDENTICAL`), loading, and empty states. Added responsive wrapping and horizontal scrolling for smaller screens.
- **Test Verification**: Created `frontend/tests/diff_viewer.test.mjs` with 10 unit tests verifying loading, empty, identical, binary, missing-source (added), removed, unified line-number gutter rendering, side-by-side aligned rendering, hunk line-number tracking, and syntax token classification. All 19 frontend unit tests pass (`npm test`). Production build (`npm run build`) succeeded.

---

#### FEAT-02: PyPI PEP 740 Cryptographic Bundle Verification Depth (Status: **RESOLVED / FIXED**)
- **Severity**: **MEDIUM**
- **Affected File**: [`backend/app/provenance/pypi.py`](file:///Users/apple12390/Veritor/backend/app/provenance/pypi.py)
- **Evidence**:
  ```python
  first_bundle = bundle_list[0]
  if isinstance(first_bundle, dict) and first_bundle.get("invalid"):
      return ProvenanceResult(status=ProvenanceStatus.INVALID, ...)
  ...
  # Extracts publisher and marks VERIFIED without invoking sigstore.verify.Verifier
  return ProvenanceResult(status=ProvenanceStatus.VERIFIED, ...)
  ```
- **Analysis**: Unlike `NpmProvenanceChecker` which feeds the attestation bundle to `sigstore.verify.Verifier` to cryptographically validate Fulcio OIDC certificates and Rekor transparency proofs against the public trust root, `PyPIProvenanceChecker` validates JSON structure and publisher metadata but does not execute offline cryptographic signature verification.
- **Remediation**: Integrate `sigstore.verify` to verify the cryptographic integrity of PEP 740 `.attestation` bundles against the Sigstore trust root.
- **Fix Applied**: Fully implemented cryptographic verification in [`backend/app/provenance/pypi.py`](file:///Users/apple12390/Veritor/backend/app/provenance/pypi.py). Created `SigstorePyPIBundleVerifier` supporting both standard Sigstore bundles (`sigstore.verify.Verifier`) and index-hosted PEP 740 attestation objects. Computes Pre-Authentication Encoding (`dsse_pae`) for Dead Simple Signing Envelopes (DSSE) and verifies ECDSA NIST P-256 signatures with SHA-256 against X.509 leaf certificates. Checks certificate validity windows and ensures expired certificates without valid transparency log timestamps are rejected (`INVALID`). Validates recognized OIDC issuers (`token.actions.githubusercontent.com`, `gitlab.com`, `accounts.google.com`), extracts source repository, commit SHA, and workflow identity from Fulcio OIDs (`1.3.6.1.4.1.57264.1.*`) and SAN URIs, and cryptographically checks that the signed subject digest matches the downloaded artifact bytes on disk. Rejects unverified publisher metadata (`NOT_VERIFIED`) without cryptographic material. Supports pluggable `BundleVerifier` for offline testing.
- **Test Verification**: Created `backend/tests/test_pypi_provenance.py` with 12 comprehensive tests verifying unavailable attestations, full cryptographic ECDSA DSSE verification, tampered signatures, mismatched artifact digests, expired certificates, untrusted OIDC issuers, unverified metadata rejection, mock verifiers, offline trust root fallback, unreadable bundle handling, missing artifacts, and remote PEP 740 integrity API fetching. All 920 backend tests pass (`pytest backend/tests`).

---

### 2. Bugs and Broken Integrations

#### INT-01: Watchlist Discrepancy Between ScannerForm and WatchlistView
- **Severity**: **MEDIUM**
- **Status**: **RESOLVED / FIXED**
- **Affected Files**: [`frontend/src/app/page.tsx:241-249`](file:///Users/apple12390/Veritor/frontend/src/app/page.tsx#L241-L249), [`frontend/src/components/WatchlistView.tsx:53-65`](file:///Users/apple12390/Veritor/frontend/src/components/WatchlistView.tsx#L53-L65), [`frontend/src/lib/storage.ts`](file:///Users/apple12390/Veritor/frontend/src/lib/storage.ts)
- **Evidence**:
  In `page.tsx`:
  ```typescript
  const handleAddToWatchlist = (ecosystem: Ecosystem, packageName: string) => {
    addToWatchlist({ ecosystem, package_name: packageName, notes: "Monitored dependency" });
    setWatchlist(getWatchlist());
  };
  ```
  `addToWatchlist` in `page.tsx` was imported strictly from `../lib/storage` (`localStorage`), bypassing the FastAPI endpoint `POST /api/v1/watchlist`.
- **Analysis**: Adding a package to the watchlist from the package scanner form saved only to the browser's local storage. The package was not registered in the backend PostgreSQL database and was never checked by the background monitoring scheduler.
- **Fix Applied**: Implemented unified persistence synchronization in `frontend/src/lib/storage.ts` (`addWatchlistItem`, `removeWatchlistItem`, and `syncWatchlist`). Backend API (`POST /api/v1/watchlist`) is now the primary persistence source; `localStorage` acts as a transparent cache and offline fallback. Updated `ScannerForm` and `WatchlistView` handlers to use `addWatchlistItem` and `removeWatchlistItem`, and added mount/refresh synchronization in `page.tsx`.
- **Test Verification**: Added frontend tests in `frontend/tests/components.test.mjs` verifying unified synchronization exports, matching ID formats (`${ecosystem}:${packageName}`), and backend-primary routing. Verified with `npm test`, `npm run typecheck`, and `npm run build`.

---

#### BUG-01: JSON Exporter Contributing Factors Key Name Mismatch
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/reports/json_exporter.py:61-75`](file:///Users/apple12390/Veritor/backend/app/reports/json_exporter.py#L61-L75)
- **Evidence**:
  ```python
  risk_summary = {
      ...
      "contributing_factors": risk.get("contributing_factors", []),
  }
  ```
  In `backend/app/schemas/scans.py:158`, the schema defines:
  ```python
  class RiskSummary(BaseModel):
      factors: list[Any] = []
      contributing_evidence: list[str] = []
  ```
- **Analysis**: The JSON exporter attempts to extract `contributing_factors`, but the model stores them under `factors`. The generated JSON export always outputs `"contributing_factors": []`.
- **Fix Applied**: Updated `json_exporter.py` to extract `factors = risk.get("factors") or risk.get("contributing_factors") or []` and populated both `"factors"`, `"contributing_factors"` (for backward compatibility), and `"contributing_evidence"`.
- **Test Verification**: Added regression test `test_generate_json_report_with_factors_key` in `backend/tests/test_report_exports.py`. Verified with `pytest backend/tests/test_report_exports.py` (4/4 passed).

---

#### BUG-02: Hardcoded Database & User in Docker Compose Postgres Healthcheck
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`docker-compose.yml:62`](file:///Users/apple12390/Veritor/docker-compose.yml#L62)
- **Evidence**:
  ```yaml
  postgres:
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-veritor}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-veritor}
      - POSTGRES_DB=${POSTGRES_DB:-veritor}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U veritor -d veritor"]
  ```
- **Analysis**: If an operator customizes `POSTGRES_USER` or `POSTGRES_DB` in `.env`, the healthcheck continues querying `-U veritor -d veritor`, causing the postgres container to report unhealthy and blocking dependent backend startup.
- **Fix Applied**: Updated healthcheck test to `["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-veritor} -d $${POSTGRES_DB:-veritor}"]`.
- **Test Verification**: Verified with `docker compose config`. The parsed command correctly resolves to `pg_isready -U ${POSTGRES_USER:-veritor} -d ${POSTGRES_DB:-veritor}` for container shell expansion.

---

#### BUG-03: Missing Per-Segment URL Encoding in File Diff API Client
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`frontend/src/lib/api.ts:144-156`](file:///Users/apple12390/Veritor/frontend/src/lib/api.ts#L144-L156)
- **Evidence**:
  ```typescript
  const cleanPath = filePath.replace(/^\/+/, "");
  const res = await fetch(`${baseUrl}/api/v1/scans/${encodeURIComponent(scanId)}/files/${cleanPath}/diff`, ...);
  ```
- **Analysis**: While `scanId` is safely URI-encoded, `cleanPath` is interpolated raw. If a file path contains `#`, `?`, or `%`, the URL structure breaks.
- **Fix Applied**: Split `cleanPath` by `/`, mapped each segment through `encodeURIComponent`, and joined with `/`.
- **Test Verification**: Added regression test `BUG-03: getFileDiff encodes each path segment correctly` in `frontend/tests/components.test.mjs`. Verified with `npm test` (8/8 passed).

---

### 3. Incorrect Assumptions

#### ASSUM-01: In-Memory Watchlist Cannot Be Checked for Updates
- **Severity**: **MEDIUM**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/monitoring/scheduler.py:63-70`](file:///Users/apple12390/Veritor/backend/app/monitoring/scheduler.py#L63-L70), [`backend/app/api/v1/watchlist.py:68-80`](file:///Users/apple12390/Veritor/backend/app/api/v1/watchlist.py#L68-L80)
- **Evidence**:
  ```python
  async def check_watchlist_now(self, session: Session | None, scan_manager: ScanManager, ...) -> WatchlistCheckResponse:
      if session is None:
          return WatchlistCheckResponse(checked_count=0, updates_detected=0, scans_triggered=0, details=[])
  ```
- **Analysis**: `ScanManager` supports full in-memory operation via `_in_memory_watchlist` when no database is configured. However, `check_watchlist_now()` assumed that a SQL session must exist. In memory mode, running `POST /api/v1/watchlist/check` immediately returned 0 checked packages, completely ignoring in-memory watchlist items.
- **Fix Applied**: Implemented `_check_in_memory_watchlist()` and `_update_in_memory_comparison()` in `ReleaseMonitoringScheduler`. Added bounded concurrency (`DEFAULT_MAX_CONCURRENCY = 4`) using `asyncio.Semaphore`, duplicate scan detection preventing redundant scan creation across checks, and an `asyncio.Lock()` to prevent overlapping scheduled or manual checks. Updated `POST /api/v1/watchlist/check` and `app/main.py` lifespan to execute in-memory checks when `session_factory` is None.
- **Test Verification**: Added `test_release_monitoring_in_memory_mode`, `test_scheduler_prevents_duplicate_scans`, and `test_scheduler_check_lock` in `backend/tests/test_release_monitoring.py`, and `test_watchlist_check_in_memory_updates` in `backend/tests/test_watchlist_api.py`. Verified with `pytest` (all passed).

---

#### ASSUM-02: Containerized `REPO_ROOT` Directory Depth
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/config.py:13-38`](file:///Users/apple12390/Veritor/backend/app/config.py#L13-L38)
- **Evidence**:
  ```python
  REPO_ROOT = Path(__file__).resolve().parents[2]
  ...
  env_file = REPO_ROOT / ".env"
  ```
- **Analysis**: On a local development machine, `parents[2]` resolves to the repository root. Inside the Docker container where code is placed in `/app/app/`, `parents[2]` resolves to `/` (the root directory), preventing the container from finding an `.env` file mounted into `/app/`.
- **Fix Applied**: Implemented `_find_repo_root(source_file)` which detects repository indicators (`.git`, `docker-compose.yml`, `.env`) on `parents[2]` for local development, and detects container roots (`alembic.ini`, `pyproject.toml`) on `parents[1]` (`/app`) for Docker containers. Additionally configured `env_file=(REPO_ROOT / ".env", Path.cwd() / ".env", ".env")`.
- **Test Verification**: Added regression test `test_repo_root_resolution` in `backend/tests/test_app.py` verifying both local development and simulated container directory structures. Verified with `pytest backend/tests/test_app.py` (12/12 passed).
  ```
- **Analysis**: On a local development machine, `parents[2]` resolves to the repository root. Inside the Docker container where code is placed in `/app/app/`, `parents[2]` resolves to `/` (the root directory), preventing the container from finding an `.env` file mounted into `/app/`.
- **Remediation**: Check both `REPO_ROOT / ".env"` and `Path.cwd() / ".env"`.

---

### 4. Security Vulnerabilities & Defenses

#### SEC-02: AI Prompt Delimitation Defense Against Prompt Injection
- **Severity**: **MEDIUM**
- **Affected File**: [`backend/app/ai/investigator.py:88-120`](file:///Users/apple12390/Veritor/backend/app/ai/investigator.py#L88-L120)
- **Analysis**: Veritor strictly enforces that package code is never executed and that the AI cannot alter deterministic risk scores. However, diff excerpts and install script lines are passed directly in JSON without specialized delimiter tags (such as XML `<untrusted_content>` tags). A malicious package containing adversarial instructions could attempt prompt injection against the AI narrative summary.
- **Remediation**: Wrap all untrusted diff excerpts and script text in `<untrusted_package_data>` delimiters with explicit instructions to treat all text within as passive literal strings.

---

### 5. Performance Bottlenecks

#### PERF-01: Repetitive Small Synchronous File IO During Comparison
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/comparison/trees.py`](file:///Users/apple12390/Veritor/backend/app/comparison/trees.py)
- **Analysis**: During archive inventory comparison, `_manifest_name` and file classifiers repeatedly invoke `tree.read(path, max_bytes)` for package configurations and declarations. On packages with thousands of files or nested monorepo structures, repeated random filesystem reads introduced unnecessary IO and SHA-256 recalculation overhead.
- **Fix Applied**: Added bounded in-memory read caching (`self._cache: dict[str, bytes]`) to `FileTree`, keyed by the canonical file path in the underlying inventory. Sub-scoped trees (such as monorepo source package views) inherit the parent inventory's cache (`source = FileTree(source_inventory, directory, cache=repository._cache)`), serving subsequent reads directly from memory in $O(1)$ time.
- **Test & Benchmark Verification**: Added `test_file_tree_caching_and_hit_counts` and reproducible fixture benchmark `test_comparison_performance_benchmark` in [`backend/tests/test_comparison.py`](file:///Users/apple12390/Veritor/backend/tests/test_comparison.py). Benchmark comparison completes in under 0.1s with zero redundant disk reads on cached files.

---

#### PERF-02: Sequential Watchlist Update Polling
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/monitoring/scheduler.py`](file:///Users/apple12390/Veritor/backend/app/monitoring/scheduler.py)
- **Analysis**: The background release monitor checked packages sequentially with an artificial `await asyncio.sleep(self.request_delay_seconds)` between individual items. For larger watchlists, sequential checks caused unnecessary latency.
- **Fix Applied**: Implemented bounded concurrent polling across both database and in-memory watchlist modes. Individual package registry queries run concurrently using `asyncio.gather(*tasks)` bounded by `asyncio.Semaphore(self.max_concurrency)`. Database session updates and scan creation are safely aggregated after all HTTP responses resolve, preventing concurrency bugs and database lock contention while strictly respecting rate-limit delays and HTTP timeouts.
- **Test Verification**: Verified through `backend/tests/test_release_monitoring.py` and `backend/tests/test_concurrency_and_stress.py` (all 19 tests passed). Bounded concurrency prevents overlapping scans and registry overloading.

---

### 6. Missing Tests

#### TST-01: Frontend Test Suite Lacks Real DOM & Component Integration Tests (Status: **RESOLVED / FIXED**)
- **Severity**: **HIGH**
- **Affected File**: [`frontend/tests/components.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/components.test.mjs)
- **Evidence**:
  ```javascript
  test("all required frontend components exist and export functional elements", () => {
    ...
    assert.match(content, comp.match, `Component must define export in ${comp.file}`);
  });
  ```
- **Analysis**: The original frontend tests passed solely by checking file existence and running regex searches on TypeScript source text. There were no unit or integration tests verifying that components render in the DOM, handle form validation and submission, update watchlist states, fetch API data, format risk scores, or handle user interactions.
- **Remediation**: Introduce React Testing Library, JSDOM, and Node's test runner to test component rendering, user interactions, network boundary mocking, and state updates across `ScannerForm`, `ReportDashboard`, `DiffViewer`, `WatchlistView`, and the API client.
- **Fix Applied**: Configured `@testing-library/react`, `@testing-library/dom`, and `jsdom` with Node.js test runner. Built a reusable DOM test runner harness in [`frontend/tests/dom_setup.mjs`](file:///Users/apple12390/Veritor/frontend/tests/dom_setup.mjs) initializing JSDOM window/document/navigator globals, TypeScript on-the-fly transpilation (`loadTsModule`), and network boundary mocking (`mockFetch`). Developed extensive component and API test suites:
  - [`frontend/tests/scanner_form.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/scanner_form.test.mjs) (10 tests): Form field rendering, ecosystem switching (npm <-> PyPI), empty package validation, version requirement & `latest` tag rejection, npm semver & PyPI PEP 440 validation, valid form submissions, watchlist triggers, loading and disabled states.
  - [`frontend/tests/watchlist.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/watchlist.test.mjs) (9 tests): Empty state rendering, monitored package table rendering, package addition input validation, API addition & refresh triggers, package removal & refresh triggers, update check loading/success/error displays, backend synchronization updating local fallback cache, and offline fallback during network partition.
  - [`frontend/tests/diff_viewer.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/diff_viewer.test.mjs) (10 tests): Loading & empty states, identical clean file banner, binary file warnings, missing source indicators, removed in package indicators, unified mode gutter & line numbers, side-by-side mode aligned cells, hunk line-number tracking, and syntax highlighting.
  - [`frontend/tests/report_dashboard.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/report_dashboard.test.mjs) (6 tests): Risk score header and level badges across all risk levels (CRITICAL, HIGH, MEDIUM), file comparison metrics, tab navigation switching (`files`, `findings`, `provenance`, `ai`), release evolution delta comparisons, and JSON export API blob generation.
  - [`frontend/tests/api_client.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/api_client.test.mjs) (11 tests): `ApiError` instantiation, `getApiBaseUrl`/`setApiBaseUrl` persistence, JSON error extraction (`detail`, `error.message`, `error.details`, `message`), non-JSON error bodies, `createScan`, per-segment URL encoding in `getFileDiff` (`BUG-03`), watchlist removal status codes, backend health checks, and Ollama connection status.
  - Preserved existing static contract tests in [`frontend/tests/components.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/components.test.mjs) (9 tests).
- **Test Verification**: All 55 frontend tests pass (`npm test` in ~890ms). TypeScript checking (`npm run typecheck`), ESLint (`npm run lint`), and production Next.js build (`npm run build`) all pass with zero errors.

---

#### TST-02: Lacks Concurrent Stress Testing (Status: **RESOLVED / FIXED**)
- **Severity**: **MEDIUM**
- **Affected Files**: `backend/tests/test_scan_pipeline.py`, `backend/tests/test_scan_api.py`
- **Analysis**: While `ScanManager` uses an `asyncio.Lock` for scan creation, there were no stress tests simulating concurrent scan submissions on identical packages or multiple simultaneous scans competing for work directories and database sessions.
- **Remediation**: Add pytest test cases utilizing `asyncio.gather` to execute concurrent scan creations, duplicate deduplication, work directory isolation, archive extraction, database session isolation, scheduler overlap prevention, cancellation cleanup, Ollama timeout resilience, and API rate-limit handling.
- **Fix Applied**: Implemented comprehensive concurrency and stress test suite in [`backend/tests/test_concurrency_and_stress.py`](file:///Users/apple12390/Veritor/backend/tests/test_concurrency_and_stress.py) with 11 reproducible test scenarios:
  1. `test_concurrent_multiple_simultaneous_scans`: Verifies 5 simultaneous scans across different packages complete without deadlocks, state cross-talk, or corrupted reports.
  2. `test_concurrent_duplicate_scan_requests`: Verifies concurrent duplicate submissions receive unique UUIDs and execute safely in parallel.
  3. `test_shared_temporary_directory_isolation`: Verifies that concurrent scans operating on packages with conflicting internal filenames maintain strict filesystem isolation under distinct UUID work directories.
  4. `test_concurrent_archive_extraction`: Verifies thread safety during parallel extraction of 8 archives via worker threads without archive corruption.
  5. `test_database_session_isolation_under_concurrency`: Verifies 5 concurrent scans persisting to SQLite across independent DB sessions commit cleanly without database lock errors.
  6. `test_scheduler_overlap_prevention`: Verifies `ReleaseMonitoringScheduler._check_lock` prevents redundant overlapping package checks when a check is already active.
  7. `test_scheduler_bounded_concurrency_semaphore`: Verifies watchlist update checks strictly enforce `DEFAULT_MAX_CONCURRENCY = 4` using `asyncio.Semaphore`.
  8. `test_scan_cancellation_and_resource_cleanup`: Verifies cancelling an active scan cleans up temporary disk directories via `finally:` blocks without orphaned leaks.
  9. `test_pipeline_failure_cleanup`: Verifies that download/extraction failures transition scans to `FAILED` and remove temporary directories.
  10. `test_ollama_timeout_graceful_handling`: Verifies Ollama inference timeouts fail gracefully to `UNAVAILABLE`/`FAILED` while preserving deterministic findings and risk scores.
  11. `test_external_api_rate_limit_behavior`: Verifies HTTP 429 Too Many Requests errors are caught cleanly, marked `FAILED`, and release resources without infinite retries.
- **Test Verification**: All 11 tests in `test_concurrency_and_stress.py` pass in 0.62s. Full backend suite passes (931 passed). Mypy and Ruff formatting checks pass with zero errors.

---

#### TST-03: Lacks Database Migration Rollback Tests
- **Severity**: **MEDIUM**
- **Affected File**: `backend/alembic/versions/`
- **Analysis**: The database test suite previously executed tests against in-memory SQLite tables initialized via `Base.metadata.create_all(engine)`. Alembic migration scripts (`001_initial_schema.py` and `002_watchlist_monitoring.py`) were never exercised in automated CI tests for both `upgrade` and `downgrade`.
- **Remediation & Fix**:
  Implemented comprehensive automated database migration test suite in [`backend/tests/test_database_migrations.py`](file:///Users/apple12390/Veritor/backend/tests/test_database_migrations.py):
  1. **Isolated Test Database Infrastructure**: Creates a dynamically-named temporary database (`veritor_test_mig_<uuid>`) via superuser connection (`autocommit=True`), guaranteeing zero interference with production or development databases. Automatically disconnects lingering backend processes (`pg_terminate_backend`) and drops the temporary database during test fixture teardown.
  2. **Step 1 — Upgrade to Head**: Executes `command.upgrade(cfg, "head")` from empty database.
  3. **Step 2 — Schema Creation & Table Inventory**: Inspects database metadata and verifies all expected tables (`packages`, `package_versions`, `scans`, `scan_reports`, `file_comparisons`, `security_findings`, `provenance_results`, `ai_explanations`, `watchlist_entries`, and `alembic_version`).
  4. **Step 3 — Required Columns & Indexes**: Asserts column presence including release monitoring columns added in revision `002` (`latest_version`, `has_update`, `last_checked_at`, `diff_summary_json`), scan state tracking columns, and performance indexes (`ix_packages_ecosystem_name`, `ix_scans_pkg_ver`, `ix_scans_created_at`, `ix_watchlist_ecosystem_package`).
  5. **Step 4 — Foreign-Key Constraints & Cascade Deletions**: Validates package-version-scan-report entity relationship hierarchy, verifies cascade deletion removes associated `ScanReport` and `SecurityFinding` records upon scan removal, and asserts `IntegrityError` when attempting invalid foreign key insertions on PostgreSQL.
  6. **Step 5 — Application Operations**: Exercises `ScanRepository` methods on the migrated schema: `save_scan()`, `get_scan()`, `save_report()`, `get_report()`, `add_watchlist_entry()`, `get_watchlist()`, `get_watchlist_entry()`, release monitoring updates, and `remove_watchlist_entry()`.
  7. **Step 6 — Downgrade to Base**: Executes partial downgrade to `001_initial_schema` verifying column drops on `watchlist_entries`, followed by full downgrade `command.downgrade(cfg, "base")` verifying complete removal of all application tables.
  8. **Step 7 — Re-upgrade After Downgrade**: Executes `command.upgrade(cfg, "head")` following downgrade to base and re-tests application operations to ensure idempotent schema re-application.
- **Test Verification**:
  - `test_sqlite_migration_lifecycle`: PASSED (0.37s)
  - `test_postgres_migration_lifecycle`: PASSED on live PostgreSQL (0.50s)
  - Integrated with GitHub Actions CI via PostgreSQL service container and `VERITOR_TEST_DATABASE_URL` environment configuration.

---

### 7. Duplicate or Unused Code

#### CODE-01: Unused `package_dir` Parameter in AI Investigator
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/ai/investigator.py:59`](file:///Users/apple12390/Veritor/backend/app/ai/investigator.py#L59)
- **Analysis**: The `package_dir` parameter was accepted by `AIInvestigator.investigate` but was never referenced in prompt building or analysis.
- **Fix Applied**: Verified references across the codebase (`backend/app/scans/pipeline.py`, `backend/app/analysis/service.py`, `backend/tests/test_ai_investigator.py`) and removed `package_dir` and the unused `Path` import from `AIInvestigator.investigate`. All callsites were updated cleanly.

---

#### FEAT-03: Multi-Host Source Resolution & Adapters
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected File**: [`backend/app/source/`](file:///Users/apple12390/Veritor/backend/app/source/)
- **Analysis**: Source code resolution was previously restricted to GitHub. Any packages hosted on GitLab, Bitbucket, or self-hosted platforms returned `UNSUPPORTED_HOST` without attempting discovery.
- **Fix Applied**:
  1. Designed `SourceHostAdapter` protocol in [`backend/app/source/base.py`](file:///Users/apple12390/Veritor/backend/app/source/base.py).
  2. Implemented `GitLabSourceResolver` in [`backend/app/source/gitlab.py`](file:///Users/apple12390/Veritor/backend/app/source/gitlab.py) with repository URL parsing (`owner/project` and nested `group/subgroup/project`), Git smart-HTTP `info/refs` packet-line tag and commit resolution, and direct commit tarball download (`/-/archive/{commit}/...`).
  3. Implemented `BitbucketSourceResolver` in [`backend/app/source/bitbucket.py`](file:///Users/apple12390/Veritor/backend/app/source/bitbucket.py) with repository URL parsing, git refs discovery, and commit tarball retrieval (`/get/{commit}.tar.gz`).
  4. Implemented `MultiHostSourceResolver` in [`backend/app/source/resolvers.py`](file:///Users/apple12390/Veritor/backend/app/source/resolvers.py) dispatching requests to GitHub, GitLab, and Bitbucket adapters.
  5. Honestly returns `UNCERTAIN` with `UncertainReason.UNSUPPORTED_HOST` for unsupported hosts (e.g. SourceForge, custom internal hosts) and `REPOSITORY_NOT_FOUND` / `NO_MATCHING_TAG` when repositories or tags cannot be verified.
- **Test Verification**: Added 12 unit tests in [`backend/tests/test_source_adapters.py`](file:///Users/apple12390/Veritor/backend/tests/test_source_adapters.py) verifying protocol conformance, URL parsing, tag matching, commit matching, archive downloading, multi-host dispatching, and honest `UNSUPPORTED_HOST` error reporting. All 12 tests pass.

---

#### CODE-02: Dual Persistence Model Drift (Local Storage vs Postgres)
- **Severity**: **LOW**
- **Status**: **RESOLVED / FIXED**
- **Affected Files**: `frontend/src/lib/storage.ts` vs `frontend/src/lib/api.ts`
- **Analysis**: Scan history and watchlist items were maintained independently in both `localStorage` and backend PostgreSQL. This dual persistence caused state drift when switching devices or clearing browser cache.
- **Fix Applied**: Established the backend API as the primary source of truth in `frontend/src/lib/storage.ts`, providing `syncWatchlist()`, `addWatchlistItem()`, and `removeWatchlistItem()`. `localStorage` now serves as an offline fallback and cache, and is automatically updated during backend operations to prevent state divergence.
- **Test Verification**: Added regression test in `frontend/tests/components.test.mjs` verifying synchronized persistence and ID parity between backend and local storage. Verified with `cd frontend && npm test`.

---

## Technical Debt & Health Scorecard

| Subsystem | Health Grade | Technical Depth | Notes |
| :--- | :---: | :---: | :--- |
| **npm Adapter & Metadata** | **A+** | High | Robust SHA-512 verification, manifest spoofing detection |
| **PyPI Adapter** | **A-** | High | PEP 440, sdist/wheel handling, domain verification |
| **Safe Archive Extraction** | **A+** | Research-grade | Zip-slip, decompression bomb, and header bounds enforcement |
| **Source Resolver (GitHub)** | **A+** | Research-grade | Zero fallback to default branches; smart-HTTP tag resolution |
| **Artifact Classifier** | **A** | High | Evidence-backed AST and sourcemap reverse tracing |
| **Static Security Scanner** | **B+** | High | Tree-Sitter JS/TS rules excellent; needs Python AST analyzer |
| **Provenance Engine** | **A-** | High | Full Sigstore npm verification; PyPI needs cryptographic verifier |
| **Deterministic Risk Engine** | **A+** | Research-grade | Strict 0-100 scoring with hard floors and explainability |
| **AI Investigator** | **A** | High | Strong guardrails preventing risk overrides and hallucinations |
| **REST APIs & Backend** | **A** | High | Comprehensive asynchronous progression tracking and schemas |
| **Database & Persistence** | **A-** | High | Clean SQLAlchemy models; needs in-memory watchlist check |
| **Monitoring & Comparison** | **A-** | High | Accurate release-to-release delta tracking |
| **Report Exports (JSON/PDF)** | **A-** | High | Executive PDF and hashed JSON; fix factor key mapping |
| **Frontend UI (Next.js 16)** | **B+** | High | Polished dark UI; needs split-diff rendering & real DOM tests |
| **Docker & Packaging** | **A-** | High | Secure non-root users; fix healthcheck parameterization |
| **CI/CD Pipelines** | **A** | High | Multi-arch GHCR publishing, matrix tests, SAST scanners |

---

## Prioritized Remediation Roadmap

1. **Phase 1: Quick Fixes (High ROI / Immediate)**
   - Fix JSON export factor key mapping (`risk.get("factors")`).
   - Fix Postgres healthcheck command in `docker-compose.yml`.
   - Connect ScannerForm "Add to Watchlist" to backend API in `page.tsx`.
   - Add in-memory watchlist checking branch in `scheduler.py`.

2. **Phase 2: Technical Depth & Core Capabilities**
   - Implement Python AST security analyzer for PyPI packages (`.py` files).
   - Implement split / side-by-side diff table rendering in `DiffViewer.tsx`.
   - Integrate `sigstore.verify` cryptographic verification for PyPI PEP 740 bundles.

3. **Phase 3: Testing & Quality Assurance**
   - Add React component unit and integration tests using React Testing Library.
   - Add Alembic migration upgrade/downgrade test suite.
   - Add concurrent scan stress tests.

