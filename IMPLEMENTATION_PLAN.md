# Implementation Plan

The backend scan pipeline, API endpoints (POST /api/v1/scans, GET status, report, findings,
files, diffs), retrieval and comparison orchestration, generated artifact intelligence,
static AST security scanning, provenance checks, deterministic risk scoring, and the Ollama AI
investigator (qwen2.5-coder:7b) are implemented and tested.

## Goal

Given a package and version on npm or PyPI, compare the published artifact with
its source repository, explain each difference with evidence, and flag
modifications that cannot be explained or that add risky behaviour.

## Principles

- **Evidence first.** Deterministic code analysis produces the findings. Models
  sort and interpret them afterwards.
- **Models cannot clear hard evidence.** A model may not downgrade a finding
  such as an untraceable new install script.
- **Package contents are untrusted.** Never install or execute them. Pass them
  to models as delimited data, never as instructions.
- **Everything runs locally.** Models run through Ollama, one at a time, to fit
  a 16 GB laptop.
- **Report uncertainty.** "Could not verify" is a separate result from "clean".

## Phases

### Phase 0: Scaffold (done)

Repository structure, placeholder frontend, FastAPI health endpoint, Python
configuration, CI, license and docs.

### API foundation (done)

Modular routes, settings, logging, schemas, error handling, CORS, `GET /health`,
and scan orchestration with background tasks, real status progression, report,
findings, file inventory, and diff endpoints.

### Phase 1: Fetch artifacts (done)

- Done for npm: `PackageAdapter` interface, exact-version metadata, and tarball
  download verified against registry hashes.
- Done: safe extraction and file inventory for npm and GitHub archives preventing
  symlink traversal, path escaping, and archive bombs.
- Done: compare registry metadata with the `package.json` inside the tarball to
  detect metadata spoofing or hidden install scripts.
- To do: PyPI adapter.

### Phase 2: Locate source (done)

- Done for GitHub: find the repository from package metadata, match the version
  to a commit using recorded commits, tags, and heuristics, record the method and
  confidence, and download the archive for that exact commit.
- A version with no established match is `UNCERTAIN`. No default branch is ever
  used in its place.
- To do: support repositories outside GitHub (GitLab, Bitbucket).

### Phase 3: Compare & Generated Artifact Intelligence (done)

- Done: compare inventories by SHA-256, with per-file JSON evidence and text
  diffs. Each file is identical, added, removed, modified, binary-different or
  renamed. Renames need an exact, unambiguous content match.
- Done: `artifact_classifier.py` analyzes `package.json`, `tsconfig.json`, bundler
  configs, entry points, source maps, counterparts, token similarity, and affirmative
  suspicious indicators.
- Classifies files strictly by evidence into:
  - `LIKELY_GENERATED`: supported by build pipeline and source relationship evidence.
  - `SUSPICIOUS`: deceptive source maps, unlinked execution in install scripts,
    obfuscated packing, or unexpected executable bits.
  - `UNCERTAIN`: when evidence is inconclusive. Never blindly whitelists `dist/`,
    `build/`, or `lib/`.
- Done: confirm the `package.json` at the matched commit has the same name and
  version, and report any disagreement as a warning.

### Phase 4: Static Security Scanner & Provenance / Risk Engine (done)

- Done: AST-based scanning for JavaScript and TypeScript (supporting JS, MJS, CJS,
  JSX, TS, MTS, CTS, TSX) using Tree-Sitter without ever executing untrusted code.
- Done: analyze added and modified files across 7 primary categories:
  1. `eval()` and `new Function()` dynamic execution (`EXEC-001` through `EXEC-005`).
  2. `child_process` execution and dangerous shell invocation (`PROC-001` through `PROC-005`).
  3. `process.env` access, credential-like variables, and whole-env dumping (`ENV-001` through `ENV-003`).
  4. Unexpected outbound network calls, data collectors, and public IP calls (`NET-001` through `NET-003`).
  5. Base64 runtime decoding, character code generation, and obfuscator names (`OBF-001` through `OBF-004`).
  6. Suspicious filesystem operations on credentials or startup files (`FS-001`, `FS-002`).
  7. Lifecycle scripts (`preinstall`, `install`, `postinstall`) tracked vs repository (`LIFE-001` through `LIFE-007`).
- Done: multi-signal correlation (`CORR-001` through `CORR-005`) for credentials + network, decoding + execution, network + execution, obfuscation + sensitive API, and sensitive behavior at install.
- Done: contract validation: every finding includes `rule_id`, `path`, `line`, `severity`, `evidence`, `explanation`, `confidence`, and `recommended_action`.
- Done: source-to-package differential scanning: pre-existing source patterns are separated so ordinary API usage is never treated as malicious.
- Done: integration with artifact intelligence (suspicious artifacts elevate finding confidence).
- Done (Part A — Provenance):
  - Check npm SLSA provenance attestations under Sigstore public trust root.
  - Inspect GitHub Actions build identity (Fulcio OID certificate extensions for source repository, commit, ref, workflow, and OIDC issuer).
  - Evaluate package integrity metadata against actual tarball SHA-512 / SHA-1 bytes.
  - Strict statuses: `VERIFIED`, `NOT_VERIFIED`, `UNAVAILABLE`, `INVALID`, `UNCERTAIN`.
  - Guardrails: Pydantic model validator prevents claiming verification based on metadata alone.
- Done (Part B — Risk Engine):
  - Deterministic 0–100 heuristic scoring derived from unexpected package differences, security findings, artifact uncertainty, source matching confidence, provenance results, and unexpected lifecycle scripts.
  - Returns complete contract: `level`, `score`, `contributing_evidence`, `confidence`, `recommendations`, and `limitations`.
  - Core safety rules: missing provenance alone awards 0 points and never implies maliciousness; clean findings with uncertain source or binaries does not imply safety.

### Phase 5: AI Investigator (done)

- Connects to Ollama with `qwen2.5-coder:7b` to explain findings with structured JSON output.
- Supplies real deterministic findings and source/package excerpts; model is barred from
  inventing evidence or altering deterministic risk results.
- Schema validation with Pydantic (`FindingExplanation`, `AIInvestigationResult`).
- Automated graceful offline fallback when Ollama is unavailable.

### Phase 6: Scan Orchestration & REST Endpoints (done)

- Full pipeline wiring: `Package input → npm fetcher → GitHub source resolver → safe extraction → inventory → comparison → artifact classification → security scanner → provenance checker → risk engine → AI investigator → integrity report`.
- Real scan statuses and progression tracking (no fake timers or synthetic progress).
- Complete REST API endpoints:
  - `POST /api/v1/scans`: Initiates and queues asynchronous scans.
  - `GET /api/v1/scans/{scan_id}`: Real-time scan state, stage, and progress percentage.
  - `GET /api/v1/scans/{scan_id}/report`: Full analysis report.
  - `GET /api/v1/scans/{scan_id}/files`: Complete file inventory and comparison classifications.
  - `GET /api/v1/scans/{scan_id}/files/{file_id}/diff`: File diff for a specific file by path or index.
  - `GET /api/v1/scans/{scan_id}/findings`: Security findings and AI investigator explanations.
- Validated with end-to-end live npm package scan (`left-pad@1.3.0`) and mock integration tests.
- Production-grade GitHub Actions CI/CD workflows (CI & Release).

### Phase 7: Complete Veritor Frontend (done)

- Premium responsive dark cybersecurity interface built with Next.js, TypeScript, Tailwind CSS, and Lucide icons.
- Complete implementation of all 11 core user experience modules:
  1. **Landing Page**: Supply chain verification value props, feature cards, and instant 1-click sample package triggers.
  2. **Package Scanner**: Real-time validation for npm semver and PyPI PEP 440 formats, rejecting invalid formats or unpinned tags.
  3. **Real-time Progress Tracker**: Live polling of FastAPI scan stages (`fetching_metadata`, `resolving_source`, `comparing`, `security_scanning`, `checking_provenance`, `scoring_risk`, `ai_investigation`, `completed`) with progress percentage and error handling.
  4. **Integrity Report Dashboard**: 0–100 deterministic risk score dial, risk level badges, contributing factors breakdown, hard security floors, confidence score, recommendations, and full JSON export.
  5. **File Explorer & Filters**: File tree and list with multi-criteria filtering by artifact classification (`LIKELY_GENERATED`, `SUSPICIOUS`, `UNCERTAIN`, `SOURCE_AUTHENTIC`) and status (`ADDED`, `MODIFIED`, `REMOVED`, `IDENTICAL`).
  6. **Diff Viewer**: Unified and side-by-side split diff display with line numbers, addition/deletion styling, metadata headers, and clipboard copy.
  7. **Security Findings Viewer**: AST findings breakdown by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), code evidence snippets, line numbers, and AI behavioral analysis.
  8. **Provenance Card**: Sigstore attestation verification status, GitHub Actions workflow identity, commit SHA match, and SHA-512 package integrity check.
  9. **Scan History**: Persistent `localStorage` history table with quick reload, score badges, timestamps, and history clearing.
  10. **Package Watchlist**: Persistent watchlist allowing users to monitor critical packages with instant scan triggers.
  11. **Settings & Infrastructure**: Backend API URL configuration, live FastAPI `/health` status, and local Ollama connection test showing available models (`qwen2.5-coder:7b`, `phi4-mini`).
- Verified with ESLint (0 errors, 0 warnings), TypeScript (`next typegen && tsc --noEmit`), automated tests (`node --test`), and production build (`next build --webpack`).

### Phase 8: Persistence & PyPI Ecosystem Support (done)

- **Database Persistence**:
  - PostgreSQL backing with SQLAlchemy 2.0 style ORM models and Alembic database migrations.
  - Complete entity schemas: `packages`, `package_versions`, `scans`, `scan_reports`, `file_comparisons`, `security_findings`, `provenance_results`, `ai_explanations`, and `watchlist_entries`.
  - `ScanRepository` providing clean persistence and reopening of historical scans, reports, file diffs, findings, and watchlist items.
  - Database fallback: seamless graceful fallback to memory when database credentials are not configured, preserving 100% offline and standalone capability.
  - REST endpoints for watchlist management (`GET`, `POST`, `DELETE /api/v1/watchlist`).
  - Docker Compose service definition for PostgreSQL 16 container with persistent volumes and healthchecks.
- **PyPI Ecosystem Support**:
  - `PyPIAdapter` querying the official PyPI JSON API with exact PEP 440 version resolution.
  - Prioritized release artifact download for source distributions (`.tar.gz`) and binary wheels (`.whl`), verifying integrity against registry SHA-256 digests and domain enforcement (`files.pythonhosted.org`).
  - PEP 508 dependency parsing and upstream GitHub / GitLab source repository discovery.
  - Safe extraction for `.whl` and `.zip` archives with path traversal prevention, anti-zip-bomb compression ratio limits, entry depth/size enforcement, and safe 0600 file permissions.
  - PyPI PEP 740 Sigstore digital attestation provenance checker (`PyPIProvenanceChecker`) returning `VERIFIED`, `NOT_VERIFIED`, `UNAVAILABLE`, `INVALID`, or `UNCERTAIN`.
  - Unified pipeline integration: PyPI packages reuse the exact same inventory comparison, artifact classification, AST security scanning, risk heuristic engine, and AI investigator without duplicating business logic.

### Phase 9: Release Monitoring & Comprehensive Report Exports (done)

- **Release Monitoring & Version Detection**:
  - Continuous release monitoring for both npm and PyPI packages in the watchlist.
  - Version detection engine (`fetch_latest_version`, `is_newer_version`, `check_package_update`) inspecting npm registry `dist-tags.latest` and PyPI JSON API `info.version`.
  - On-demand updates check (`POST /api/v1/watchlist/check`) and background scheduled monitor with sensible rate limits and request delays.
  - Automated background scan triggering for newly published versions with status tracking (`GET /api/v1/watchlist/monitoring-status`).
- **Release-to-Release Differential Comparison**:
  - `ReleaseComparator` comparing the newest analyzed release against the previous baseline release.
  - Risk changes tracking: score delta, risk level shifts, and explicit elevated risk warnings.
  - File changes breakdown: newly added files, newly modified files, newly removed files, and newly introduced suspicious build artifacts.
  - Security finding evolution: newly introduced security findings, resolved findings, and persistent findings.
  - Provenance changes: tracks attestation status changes and flags any security downgrades.
  - Explainable human-readable summary synthesising risk progression and critical changes.
- **Comprehensive Report Exports**:
  - **Structured JSON Export** (`GET /api/v1/scans/{scan_id}/export/json`):
    - Standardized export format with `export_metadata` (schema version, exported timestamp, SHA-256 integrity hash).
    - Complete package metadata, source repository information, comparison statistics, AST security findings, provenance verification, deterministic risk assessment, and AI investigation explanations.
  - **Executive PDF Export** (`GET /api/v1/scans/{scan_id}/export/pdf`):
    - ReportLab PDF document generator producing a clean cybersecurity report.
    - Color-coded risk score dial, provenance attestation table, source matching summary, file comparison statistics, AST security findings table with evidence snippets, AI behavioral investigation, recommendations, and analysis limitations.
- **Frontend Integration**:
  - Report dashboard download buttons for instantaneous 1-click JSON and PDF exports.
  - "Release Evolution" card displaying release-to-release score deltas, newly added suspicious artifacts, new findings, and file diff summaries.
  - Watchlist view connected to backend API with live update badges (`NEW RELEASE AVAILABLE`), on-demand check button with animated spinner, and instant scan triggers.
- **API Endpoints**:
  - `GET /api/v1/scans/{scan_id}/export/json`: Download package report as structured JSON.
  - `GET /api/v1/scans/{scan_id}/export/pdf`: Download package report as styled PDF.
  - `GET /api/v1/scans/{scan_id}/compare-previous`: Compare scan against the immediate prior release.
  - `GET /api/v1/scans/compare`: Arbitrary two-scan release comparison by ID.
  - `GET /api/v1/watchlist`: List all monitored packages with update statuses.
  - `POST /api/v1/watchlist`: Add package to monitored watchlist.
  - `DELETE /api/v1/watchlist/{entry_id}`: Remove package from watchlist.
  - `POST /api/v1/watchlist/check`: Trigger on-demand version update check across watchlist.
  - `GET /api/v1/watchlist/monitoring-status`: Query monitoring background scheduler metrics.
  - `GET /api/v1/watchlist/{entry_id}/compare`: Get release comparison for a watchlisted package.

### Phase 10: Validation, CI/CD, Documentation, and Release Preparation (done)

- **Comprehensive Scenario Verifications** (`backend/tests/test_scenario_verifications.py`):
  - Verified 6 critical supply chain evaluation scenarios with automated pytest assertions:
    1. *Legitimate npm package with generated files*: Minified build artifacts (`dist/index.min.js`) with accompanying source maps correctly classified as `LIKELY_GENERATED`, producing low risk score.
    2. *Package with harmless simulated suspicious modifications*: Tampered package injecting an unmapped postinstall lifecycle script, unmapped `eval()`, and credential environment dumping triggers `LIFE-001`, `EXEC-001`, and `ENV-001` AST findings, elevating risk score to `HIGH`/`CRITICAL`.
    3. *Package with missing source release*: Missing commit/tag strictly produces `UNCERTAIN` match status; Veritor never falls back to the repository's default branch (`main`/`master`).
    4. *Package with unavailable provenance*: Package without Sigstore attestation yields `UNAVAILABLE` status without artificially inflating risk score (missing provenance != malicious).
    5. *Scan when Ollama is unavailable*: Offline Ollama detection completes gracefully, yielding deterministic findings, risk assessment, and an explainable fallback summary without blocking or crashing the pipeline.
    6. *PyPI package analysis*: Full PyPI pipeline verification for sdist and binary wheel artifacts, metadata parity, AST security analysis, and PEP 740 provenance checks.
- **CI/CD Hardening & Automated Releases**:
  - Enhanced GitHub Actions workflow (`.github/workflows/ci.yml`) with Docker Compose validation, comprehensive backend test matrix, frontend build verification, and linting.
  - Enhanced GHCR Release workflow (`.github/workflows/release.yml`) with automated lowercase repository handling, Docker buildx multi-platform caching, semantic version tagging, and write permissions.
- **Docker Compose & Production Packaging**:
  - Dynamic environment variable configuration with resilient fallbacks across all containers.
  - Container-ready database migrations with Alembic and automatic runtime schema initialization.
- **Documentation Suite**:
  - `docs/architecture.md`: Complete system architecture, data flow diagrams, pipeline invariants, and security threat model.
  - `docs/api.md`: Comprehensive OpenAPI-aligned specification covering all scan, export, and watchlist endpoints.
  - `docs/demo.md`: Step-by-step hackathon judging and live evaluation walkthrough guide.
  - `README.md` & `hackathon.md`: Polished project overviews, badges, architecture diagrams, and quickstart guides.

---

## Final Project Status Report

### 1. Completed Features
- **Package Ecosystem Adapters**:
  - `npm` adapter: Tarball streaming, registry metadata hash verification (SHA-512, SHA-1), package.json metadata parity verification.
  - `PyPI` adapter: PEP 440 version normalization, source distribution (`.tar.gz`) and binary wheel (`.whl`) downloads, hash integrity verification, safe ZIP/TAR extraction preventing directory traversal and decompression bombs.
- **Source Repository Resolver**:
  - GitHub commit and tag resolution with exact cryptographic matching, release tag heuristics, and strict `UNCERTAIN` status when missing (zero fallback to default branch).
- **Artifact Intelligence & Classification**:
  - Heuristic classifier distinguishing `LIKELY_GENERATED` build outputs from `SUSPICIOUS` unmapped code and `UNCERTAIN` files using source maps, compiler configs, AST parity, and token similarity.
- **Static AST Security Scanner**:
  - Language-aware Tree-Sitter scanner for JavaScript/TypeScript and Python AST analyzer.
  - Detects dynamic execution (`eval`, `Function`), process execution (`child_process`), environment dumping (`process.env`), unexpected outbound networking, Base64 obfuscation, sensitive filesystem access, and suspicious lifecycle scripts.
  - Differential source filtering eliminating false positives from code present in original repository.
- **Provenance & Attestation Verification**:
  - npm Sigstore SLSA provenance verification and GitHub Actions Fulcio OID certificate extension inspection.
  - PyPI PEP 740 digital attestation verification.
  - Strict verification statuses: `VERIFIED`, `NOT_VERIFIED`, `UNAVAILABLE`, `INVALID`, `UNCERTAIN`.
- **Explainable Risk Engine**:
  - Deterministic 0–100 heuristic scoring based on unexpected diffs, security findings, artifact ambiguity, provenance status, and lifecycle scripts.
  - Explains all contributing factors, confidence levels, security recommendations, and analysis limitations.
- **AI Investigator**:
  - Local Ollama integration (`qwen2.5-coder:7b`) with Pydantic JSON schema enforcement.
  - Explains findings without ever overriding or downgrading deterministic risk scores.
  - Graceful fallback when Ollama is offline or unavailable.
- **Scan Pipeline & Asynchronous Execution**:
  - Background scan workers with real-time stage progression tracking (`GET /api/v1/scans/{id}`).
  - REST endpoints for reports, file trees, unified/split diffs, and security findings.
- **Persistence & History**:
  - PostgreSQL backing via SQLAlchemy 2.0 with Alembic migrations and automatic memory fallback for offline/test mode.
- **Continuous Release Monitoring & Comparison**:
  - Watchlist management for npm and PyPI packages.
  - Automated version update checks and background scan scheduling.
  - Release-to-release differential comparator tracking risk deltas, newly introduced suspicious files, and finding evolution.
- **Comprehensive Report Exports**:
  - Standardized JSON export with integrity checksums.
  - Professional Executive PDF export via ReportLab with risk score dials, attestation status, AST findings tables, and AI explanations.
- **Responsive Cybersecurity UI**:
  - Dark mode Next.js 16 frontend with Tailwind CSS and Lucide icons.
  - Real-time progress tracker, split diff viewer, interactive file explorer, provenance cards, scan history, watchlist, and live system health monitor.
- **Deployment & CI/CD**:
  - Multi-container `docker-compose.yml` orchestrating backend, frontend, PostgreSQL, and Ollama.
  - GitHub Actions CI matrix and release automation publishing multi-arch images to GHCR.

### 2. Incomplete Features & Future Roadmap
- **Alternative VCS Providers**: Support for GitLab, Bitbucket, and self-hosted Git repositories (currently GitHub is supported).
- **Additional Ecosystems**: Adapters for Rust (`crates.io`), Go modules (`proxy.golang.org`), and Ruby (`rubygems.org`).
- **Webhook Integrations**: Outbound notifications for Slack, Discord, and GitHub PR checks when monitored watchlist packages publish new releases.
- **Air-Gapped Sigstore Roots**: Bundled offline Sigstore trust root caches for environments with strict firewalling.
- **Hardware Token Maintainer Verification**: WebAuthn / YubiKey signing key verification for package maintainers.

### 3. Actual Test Results
- **Backend Test Suite (`pytest backend/tests`)**:
  - **893 tests executed, 893 passed** (100% pass rate in 43.12s).
  - 6/6 evaluation scenario tests passed (`test_scenario_verifications.py`).
  - Unit, integration, security scanner, provenance, risk engine, and database repository tests passed.
- **Code Quality & Static Analysis**:
  - `ruff check backend`: 0 lint errors, 0 warnings across all files.
  - `ruff format --check backend`: 102 source and test files clean and compliant.
  - `mypy --config-file backend/pyproject.toml backend/app backend/tests`: Success, no issues found in 102 source files under strict typechecking.
- **Frontend Test Suite & Build (`frontend`)**:
  - Automated tests (`node --test`): **7/7 test suites passed** (100% pass rate).
  - ESLint (`npm run lint`): 0 errors, 0 warnings (React 19 / Next.js compliant).
  - TypeScript (`npm run typecheck`): Clean typecheck across all TSX components and API clients.
  - Production build (`npm run build`): Successfully generated optimized static and dynamic routes.
- **Security Check**:
  - `bandit -r backend/app`: 0 high severity vulnerabilities identified.
  - Safe archive extractors validated against symlink traversal and zip bomb attacks.

### 4. Known Limitations
- **Local AI Hardware Dependencies**: Local inference via Ollama requires host RAM/GPU capacity for `qwen2.5-coder:7b`. In resource-constrained environments, Veritor seamlessly uses its deterministic engine.
- **Version Pinning Requirement**: Input packages must specify exact versions (e.g. `lodash@4.17.21` or `requests@2.31.0`). Semver ranges or floating tags like `latest` are rejected by design to prevent non-reproducible verification state.
- **Private Registries**: Private scoped packages requiring internal corporate credentials require local network access and auth tokens.
- **Heavy Code Packing**: Sophisticated commercial packers and heavy obfuscation are flagged as high-risk suspicious artifacts rather than deobfuscated in-flight.

### 5. Commands to Run the Application

#### Using Docker Compose (Recommended)
```bash
# Clone the repository
git clone https://github.com/ManshaAgarwal716/Veritor.git
cd Veritor

# Start all services (Backend, Frontend, PostgreSQL, Ollama)
docker compose up --build -d

# Check service health
docker compose ps
```
The frontend is available at `http://localhost:3000` and the API at `http://localhost:8000`.

#### Local Development Run (Bare Metal)
```bash
# 1. Backend
cd backend
poetry install
poetry run alembic upgrade head   # If Postgres is running, or skip for in-memory mode
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Frontend
cd ../frontend
npm install
npm run dev
```

#### Running the Full Test Suite
```bash
# Run backend tests
cd backend && poetry run pytest -v

# Run backend static analysis
poetry run ruff check .
poetry run mypy --config-file pyproject.toml app tests

# Run frontend tests and production build
cd ../frontend
npm test
npm run lint
npm run build
```

### 6. Hackathon Demonstration Workflow
1. **Launch Veritor**: Navigate to `http://localhost:3000` in your browser. Verify backend connection in the footer status badge.
2. **Demo 1 — Legitimate Clean Package**:
   - Click the **"left-pad@1.3.0"** quick example button or enter `npm:left-pad@1.3.0`.
   - Click **Verify Integrity**.
   - Observe real-time analysis stages completing in ~1-2 seconds.
   - Inspect the **Report Dashboard**: Risk Score **0 (Low)**, Source Match **VERIFIED** to exact commit, zero suspicious findings.
3. **Demo 2 — Differential Source vs Package**:
   - Navigate to the **File Explorer** and **Diff Viewer** tabs.
   - View files classified as `SOURCE_AUTHENTIC` vs `LIKELY_GENERATED`.
   - Inspect the syntax-highlighted side-by-side diff.
4. **Demo 3 — Suspicious Lifecycle Script & AST Finding**:
   - Inspect findings on simulated tampered package in test runner or live demo package.
   - Observe AST rule detections (`EXEC-001`, `ENV-001`, `LIFE-001`) with exact file and line locations, code snippets, and severity indicators.
5. **Demo 4 — PyPI Package & PEP 740 Provenance**:
   - Enter `pypi:urllib3@2.2.1` in the scanner.
   - Observe PEP 740 digital attestation verification and sdist validation.
6. **Demo 5 — Continuous Monitoring & Release Evolution**:
   - Add packages to the **Watchlist**.
   - Click **Check for Updates** to run automated version detection.
   - View the **Release Evolution** card showing score delta and new differences between versions.
7. **Demo 6 — Export Capabilities**:
   - Click **Export JSON** to download standardized audit machine-readable metadata.
   - Click **Export PDF** to download the styled executive security assessment report.

---

### Phase 11: Post-Development Technical Audit & Engineering Hardening (in progress)

- Conducted exhaustive full-stack technical audit across frontend, backend, APIs, adapters, comparison, classification, security scanner, provenance, risk scoring, AI, database, monitoring, exports, Docker, and CI/CD.
- Produced [`docs/FINAL_AUDIT.md`](docs/FINAL_AUDIT.md) cataloging 18 findings categorized by severity, affected component, concrete code evidence, and explicit remediations.
- Defined prioritized remediation roadmap:
  - Phase 1: Immediate fixes (JSON export factor keys, Docker compose Postgres healthcheck, frontend watchlist API synchronization, in-memory watchlist checking).
  - Phase 2: Technical depth enhancements (Python AST analyzer for PyPI packages, split-diff table rendering in `DiffViewer.tsx`, cryptographic verification of PEP 740 bundles via `sigstore.verify`).
  - Phase 3: Testing and reliability (React component integration tests, Alembic migration rollback verification, concurrent pipeline stress testing).

#### Completed Remediation Tasks
1. **Remediation Task 1 (Low-Risk Bugs & Configuration Fixes)**:
   - **BUG-01**: Updated JSON exporter to support `factors`, `contributing_factors`, and `contributing_evidence`.
   - **BUG-02**: Parameterized PostgreSQL Docker Compose healthcheck using configured `$${POSTGRES_USER}` and `$${POSTGRES_DB}` variables.
   - **BUG-03**: Implemented segment-by-segment `encodeURIComponent` URL path encoding in `getFileDiff`.
   - **ASSUM-02**: Corrected `REPO_ROOT` resolution via `_find_repo_root` to support both local workspaces and containerized `WORKDIR /app` environments.
2. **Remediation Task 2 (Watchlist Persistence Consistency & Concurrency)**:
   - **INT-01**: Updated `ScannerForm` and `WatchlistView` to persist watchlist entries to the backend API (`POST /api/v1/watchlist`) with `localStorage` serving strictly as an offline fallback cache.
   - **ASSUM-01**: Implemented full in-memory release monitoring and release-to-release diff computation in `ReleaseMonitoringScheduler` when running without a database (`session is None`). Added bounded concurrency (`DEFAULT_MAX_CONCURRENCY = 4`) via `asyncio.Semaphore`, duplicate scan detection, and `_check_lock` to prevent overlapping scheduled or on-demand checks.
   - **CODE-02**: Consolidated duplicate persistence logic in `frontend/src/lib/storage.ts` with `syncWatchlist()`, `addWatchlistItem()`, and `removeWatchlistItem()`, maintaining state parity and unified ID formatting (`${ecosystem}:${packageName}`).
3. **Remediation Task 3 (Native Python AST Security Analysis - SEC-01)**:
   - Implemented modular, non-executing Python AST security scanner in `backend/app/analysis/py_scanner.py` using Python's built-in `ast` module.
   - Detects all 8 suspicious threat categories: dynamic execution (`eval`, `exec`, `compile` -> `EXEC-001/002/003`), process execution (`subprocess`, `os.system`, `os.popen`, `ctypes` -> `PROC-001/002/003/004/005`), environment credential access (`os.environ`, `os.getenv` -> `ENV-001/002/003`), network communication (`requests`, `urllib`, `socket`, `httpx`, `aiohttp` -> `NET-001/002/003`), dynamic imports (`importlib.import_module`, `__import__` -> `EXEC-004/005`), suspicious filesystem paths and startup persistence writes (`FS-001/002`), runtime decoding and obfuscation (`OBF-001/002/003/004`), and install-time execution (`setup.py` -> `CORR-005`).
   - Integrated into `scannable_language()` and `analyzer.py` pipeline, ensuring `.py` files in PyPI packages are fully scanned without receiving `UNSUPPORTED_LANGUAGE` gaps.
   - Preserves deterministic risk scoring parity and schema consistency with JS/TS scanner.
   - Added unit test suite in `backend/tests/test_py_scanner.py` (12 tests passed).
4. **Remediation Task 4 (DiffViewer Split/Side-by-Side Mode - FEAT-01)**:
   - Completed both Unified and Side-by-Side (Split) diff modes in [`frontend/src/components/DiffViewer.tsx`](file:///Users/apple12390/Veritor/frontend/src/components/DiffViewer.tsx).
   - Implemented `parseUnifiedDiff()`: Parses hunk headers (`@@ -old,count +new,count @@`), tracks `oldLine` and `newLine` offsets accurately, and aligns modified lines (pairing deletion and addition sequences row-by-row with empty padding when deletion/addition counts differ) without fabricating missing lines.
   - Built dual-column `SplitDiffTable`: Sticky comparison headers ("Source Repository" vs "Published Package"), aligned line numbering, independent side-by-side cells with status coloring, and indicator badges for added files missing in source repository and removed files.
   - Implemented syntax highlighting (`highlightTokens()`) for code tokens (keywords, strings, comments, numbers, booleans) without external dependencies.
   - Added complete state handling for binary files (`diff_status === "BINARY"`), added files missing in source (`ADDED`), removed files (`REMOVED`), identical files (`IDENTICAL`), empty states, and loading states.
   - Implemented responsive horizontal scrolling and fluid layout for small screens.
   - Created React component test suite in `frontend/tests/diff_viewer.test.mjs` (10 tests) verifying DOM rendering, hunk header parsing, line alignment, and syntax highlighting.
5. **Remediation Task 5 (PyPI PEP 740 Cryptographic Attestation Verification - FEAT-02)**:
   - Replaced unverified metadata extraction with cryptographic DSSE envelope and Sigstore verification in [`backend/app/provenance/pypi.py`](file:///Users/apple12390/Veritor/backend/app/provenance/pypi.py).
   - Built `SigstorePyPIBundleVerifier` supporting both standard Sigstore bundles (`sigstore>=4,<5`, `sigstore.verify.Verifier`) and index-hosted PEP 740 attestation objects.
   - Implemented Pre-Authentication Encoding (`dsse_pae`) for Dead Simple Signing Envelopes (DSSE) and verified ECDSA NIST P-256 signatures with SHA-256 against X.509 leaf certificates.
   - Enforced strict certificate validity checking: validated validity dates (`not_valid_before_utc` and `not_valid_after_utc`), required transparency log timestamps for short-lived certificates, and explicitly rejected expired certificates without log proofs (`INVALID`).
   - Validated trusted OIDC identity providers (`token.actions.githubusercontent.com`, `gitlab.com`, `accounts.google.com`), extracted source repository and commit identity from Fulcio OIDs (`1.3.6.1.4.1.57264.1.*`) and SAN URIs, and cryptographically verified that signed subject SHA-256 digests match actual artifact bytes on disk.
   - Established strict boundary between metadata and cryptographic proof: unverified metadata payloads without cryptographic signatures are marked `NOT_VERIFIED`, while packages without attestations receive neutral `UNAVAILABLE` status (0 risk points).
   - Created comprehensive unit test suite in [`backend/tests/test_pypi_provenance.py`](file:///Users/apple12390/Veritor/backend/tests/test_pypi_provenance.py) (12 tests) verifying offline verification, tampered signatures, mismatched digests, expired certs, untrusted issuers, unverified metadata, mock verifiers, and remote PEP 740 integrity API retrieval.
   - Updated architecture documentation in [`docs/architecture.md`](file:///Users/apple12390/Veritor/docs/architecture.md).
6. **Remediation Task 6 (Frontend Testing & DOM Test Harness - TST-01)**:
   - Added `@testing-library/react`, `@testing-library/dom`, and `jsdom` to `frontend/package.json`.
   - Implemented DOM test environment in [`frontend/tests/dom_setup.mjs`](file:///Users/apple12390/Veritor/frontend/tests/dom_setup.mjs) providing JSDOM global browser environments (`window`, `document`, `navigator`, `localStorage`, `HTMLElement`, `HTMLButtonElement`, `HTMLAnchorElement`, etc.), on-the-fly TypeScript transpilation (`loadTsModule`), and boundary-level HTTP mock interception (`mockFetch`).
   - Implemented comprehensive DOM component tests in [`frontend/tests/scanner_form.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/scanner_form.test.mjs) (10 tests) covering form field rendering, ecosystem switching (npm <-> PyPI), empty package validation, version requirement & `latest` tag rejection, npm semver & PyPI PEP 440 validation, form submission for both ecosystems, watchlist triggers, loading and disabled states.
   - Implemented Watchlist DOM & synchronization tests in [`frontend/tests/watchlist.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/watchlist.test.mjs) (9 tests) covering empty state, monitored table rendering, package addition validation, API submission & refresh triggers, package deletion & refresh triggers, update checking states, backend synchronization updating local fallback cache, and network failure fallback.
   - Implemented report rendering tests in [`frontend/tests/report_dashboard.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/report_dashboard.test.mjs) (6 tests) covering risk score header and level badges across all risk levels (CRITICAL, HIGH, MEDIUM), file comparison metrics, tab navigation switching (`files`, `findings`, `provenance`, `ai`), release evolution delta comparisons, and JSON export API blob generation.
   - Implemented DiffViewer DOM tests in [`frontend/tests/diff_viewer.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/diff_viewer.test.mjs) (10 tests) covering loading & empty states, identical clean file banner, binary file warnings, missing source indicators, removed in package indicators, unified mode gutter & line numbers, side-by-side mode aligned cells, hunk line-number tracking, and syntax highlighting.
   - Implemented API client boundary tests in [`frontend/tests/api_client.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/api_client.test.mjs) (11 tests) verifying `ApiError` extraction, JSON & non-JSON error formats, `createScan`, path segment encoding in `getFileDiff` (`BUG-03`), watchlist status codes, health checks, and Ollama connection status.
   - Preserved useful static contract checks in [`frontend/tests/components.test.mjs`](file:///Users/apple12390/Veritor/frontend/tests/components.test.mjs) (9 tests).
   - All 55 frontend tests pass (`npm test`). Typecheck (`npm run typecheck`), lint (`npm run lint`), and production Next.js build (`npm run build`) pass cleanly. All 920 backend tests pass (`pytest backend/tests`).




