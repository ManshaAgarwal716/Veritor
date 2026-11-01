# Veritor Hackathon Demonstration Guide

This guide walks through demonstrating Veritor's full capabilities for **Problem 04: Published Package vs Source Code Integrity Analyzer**.

---

## 1. Quick Launch

You can run Veritor either via **Docker Compose** (recommended for evaluation) or **bare metal**.

### Option A: Docker Compose (All-in-One)

```bash
# Clone and launch all services (backend, frontend, postgres, ollama)
docker compose up --build
```

- **Frontend UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

### Option B: Bare Metal (Local Python & Node.js)

```bash
# Terminal 1 - Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

---

## 2. Recommended Live Demonstration Workflow

### Step 1: Clean npm Package with Generated Build Artifacts
1. Open the UI at [http://localhost:3000](http://localhost:3000).
2. Click the quick-fill sample button **`chalk@5.3.0`** (or `left-pad@1.3.0`).
3. Click **Analyze Package Integrity**.
4. **Observe**:
   - **Real-Time Progress Tracker**: Live progression through `fetching_metadata`, `resolving_source`, `comparing`, `security_scanning`, `checking_provenance`, `scoring_risk`.
   - **Risk Gauge**: Evaluated as **`LOW` (Score: 0/100)** with High Confidence.
   - **Artifact Intelligence**: Files in `source/` are recognized as authentic; build outputs are identified without raising false alarms.
   - **Provenance Card**: Sigstore attestation verification status is displayed with GitHub Actions workflow identity and commit SHA match.

---

### Step 2: PyPI Package Analysis
1. Select the **PyPI** ecosystem radio button.
2. Enter package name: `requests`, version: `2.31.0`.
3. Click **Analyze Package Integrity**.
4. **Observe**:
   - PyPIAdapter queries the official PyPI JSON API and downloads the `.whl` binary wheel.
   - Safe zip archive extractor validates entry depth and prevents compression bombs.
   - Code comparison maps Python package contents (`requests/`) against GitHub repository source.
   - Result: Clean match with PEP 740 provenance evaluation.

---

### Step 3: Simulated Supply Chain Attack Detection
Veritor includes unit and integration tests executing real malicious patterns without running untrusted code:
```bash
# Run simulated attack and scenario verifications
python3 -m pytest backend/tests/test_scenario_verifications.py -v
```

**Demonstration highlights**:
- **Simulated Pattern**: A release containing an unauthorized `postinstall` script with `Buffer.from('...', 'base64')`, `eval(...)`, and `child_process.exec(...)`.
- **Detection**:
  - `EXEC-001`: Dynamic code execution.
  - `PROC-001`: Subprocess execution.
  - `OBF-001`: Base64 runtime decoding.
  - `LIFE-001`: Unauthorized postinstall hook discrepancy.
- **Classification**: `setup.js` flagged as **`SUSPICIOUS`**.
- **Risk Result**: Deterministic floor rules trigger **`CRITICAL` Risk (Score: 74/100)** with clear warnings against installing the package.

---

### Step 4: Release Evolution & Watchlist Monitoring
1. In the UI, navigate to the **Watchlist** tab in the navbar.
2. Add a package to the watchlist (e.g. `npm` / `chalk` or `pypi` / `flask`).
3. Click **Check for Updates**.
4. **Observe**:
   - The on-demand update detector queries npm and PyPI registries with rate-limited delays.
   - The status badge changes to `NEW RELEASE AVAILABLE` if a newer version is published.
   - 1-Click trigger initiates analysis of the new release.
   - When viewing the scan report, observe the **Release Evolution (v1 → v2)** card:
     - Shows risk score delta (`+0 pts` or elevated delta).
     - Details file evolution (`+N added`, `~N modified`, `-N removed`).
     - Highlights newly introduced findings or newly identified suspicious build artifacts.

---

### Step 5: Executive & Technical Report Exports
1. On any completed scan report, locate the export buttons in the header:
2. **Export JSON**:
   - Downloads structured report JSON containing all comparison statistics, AST findings, risk factors, and the cryptographic SHA-256 report integrity hash.
3. **Export PDF**:
   - Downloads a ReportLab-generated cybersecurity report with risk dial badge, provenance table, file inventory summary, AST security findings table with evidence snippets, AI summary, recommendations, and analysis limitations.

---

### Step 6: Resilience & Fault Tolerance Testing
1. **Ollama Offline**:
   - Stop or disconnect Ollama. Run a scan.
   - The scan succeeds in full. Deterministic static AST findings and risk scores remain 100% authoritative. The AI section reports `OFFLINE` gracefully.
2. **Database Offline**:
   - Stop PostgreSQL.
   - The application automatically falls back to in-memory persistence and session storage, remaining completely usable.

---

## 3. Test & Verification Commands

```bash
# Full Backend Test Suite (893 tests)
python3 -m pytest backend/tests

# Static Linter & Formatting
python3 -m ruff check backend && python3 -m ruff format --check backend

# Static Type Checking
python3 -m mypy --config-file backend/pyproject.toml backend/app backend/tests

# Security SAST & Audits
python3 -m bandit -r backend/app -ll -ii

# Frontend Verification & Production Build
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```
