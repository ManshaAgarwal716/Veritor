# Veritor

[![CI](https://github.com/ManshaAgarwal716/Veritor/actions/workflows/ci.yml/badge.svg)](https://github.com/ManshaAgarwal716/Veritor/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)

Veritor compares packages published on **npm** and **PyPI** with their upstream source code repositories on GitHub, explains each difference with deterministic evidence, and flags unauthorized modifications, deceptive build artifacts, or supply chain attacks.

Built for **Problem 04: Published Package vs Source Code Integrity Analyzer**.

---

## Documentation

- **[System Architecture](docs/architecture.md)**: Technical architecture, pipeline stages, security models, and verification flow.
- **[REST API Reference](docs/api.md)**: Complete OpenAPI specification for FastAPI endpoints.
- **[Hackathon Demonstration Guide](docs/demo.md)**: Step-by-step evaluation workflows and live test commands.
- **[CI/CD & Security Architecture](docs/CI-CD.md)**: GitHub Actions workflows, GHCR Docker publishing, and vulnerability scanners.
- **[Hackathon Context & Goals](hackathon.md)**: Problem statement breakdown and original requirements.

---

## Core Capabilities

1. **Multi-Ecosystem Support**:
   - **npm**: Registry metadata validation, tarball download & SHA-512 integrity verification, `package.json` spoofing detection.
   - **PyPI**: Official JSON API resolution, binary wheel (`.whl`) and source distribution (`.tar.gz`) support, PEP 508 dependency parsing.
2. **Safe Archive Extraction**:
   - Hardened extraction preventing directory traversal (Zip Slip), symlink escapes, and compression bombs. Enforces strict size, entry count, and depth bounds with safe `0600` POSIX permissions.
3. **Strict Source Code Resolution**:
   - Matches published packages to exact GitHub commits using four verifiable tiers (`RECORDED_COMMIT_AND_TAG`, `PACKAGE_TAG`, `VERSION_TAG`, `RECORDED_COMMIT`).
   - If no exact match is proven, returns `UNCERTAIN`. Never assumes or uses a default branch.
4. **Generated Artifact Intelligence**:
   - Differentiates authentic source files from build outputs (`dist/`, `build/`) using bundler configs, TypeScript declarations, and bidirectional source map reverse-tracing.
   - Categorizes files as `SOURCE_AUTHENTIC`, `LIKELY_GENERATED`, `SUSPICIOUS`, or `UNCERTAIN`.
5. **Static AST Security Scanner**:
   - Zero code execution AST parsing for JavaScript and TypeScript via Tree-Sitter.
   - Analyzes differences across 7 primary rule families: `eval`/dynamic code (`EXEC`), subprocess execution (`PROC`), environment access (`ENV`), network exfiltration (`NET`), obfuscation (`OBF`), sensitive filesystem access (`FS`), and install scripts (`LIFE`).
   - Multi-signal correlation flags compound attack vectors (e.g. Base64 decoding + dynamic execution at install time).
6. **Cryptographic Provenance Verification**:
   - Validates Sigstore SLSA provenance attestations and Fulcio OIDC certificates against the Rekor public transparency log.
   - Evaluates PyPI PEP 740 digital attestations.
   - Invariant: Missing provenance awards 0 risk points and never implies maliciousness.
7. **Explainable Deterministic Risk Engine**:
   - 0–100 heuristic score derived purely from verifiable static evidence.
   - Hard security floors enforce minimum `HIGH` or `CRITICAL` risk ratings for severe anomalies.
   - Generates complete audit trails, contributing factors, recommendations, and limitations.
8. **Local AI Investigator**:
   - Connects locally to Ollama running `qwen2.5-coder:7b`.
   - Generates structured, schema-validated JSON explanations without altering deterministic risk verdicts.
   - Fully resilient: continues operating seamlessly with structured fallback when Ollama is offline.
9. **Continuous Release Monitoring & Evolution Engine**:
   - Monitored package watchlist with rate-limited background checks detecting newly published versions on npm and PyPI.
   - Release comparator tracks risk score deltas, newly introduced suspicious files, AST finding changes, and provenance downgrades.
10. **Executive & Technical Report Exports**:
    - **JSON Export**: Machine-readable report with cryptographic SHA-256 integrity hash.
    - **PDF Export**: ReportLab-generated cybersecurity report with risk dial gauge, provenance verification, inventory breakdown, AST finding evidence table, AI summary, and limitations.
11. **Production-Ready Interface**:
    - Dark cybersecurity theme built with Next.js 16, TypeScript, Tailwind CSS, and Lucide icons.
    - Real-time pipeline stage progress tracking, side-by-side diff viewer, interactive file tree with classification filters, and live watchlist.

---

## Project Structure

```
Veritor/
├── backend/
│   ├── app/
│   │   ├── adapters/        # npm & PyPI registry adapters
│   │   ├── ai/              # Ollama client & AI investigator
│   │   ├── analysis/        # Tree-sitter static AST security scanner
│   │   ├── api/v1/          # FastAPI REST endpoints (/scans, /watchlist)
│   │   ├── archives/        # Safe tarball & zip extractor
│   │   ├── comparison/      # Inventory diff & artifact intelligence
│   │   ├── db/              # SQLAlchemy 2.0 ORM models & session factory
│   │   ├── monitoring/      # Release detector, comparator & scheduler
│   │   ├── provenance/      # Sigstore npm & PyPI attestation checkers
│   │   ├── reports/         # Structured JSON & ReportLab PDF exporters
│   │   ├── scans/           # Scan manager & async pipeline orchestrator
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── scoring/         # Deterministic 0-100 risk heuristic engine
│   │   └── source/          # GitHub repository & commit resolution
│   ├── alembic/             # Database schema migrations
│   ├── tests/               # 893 pytest integration & unit tests
│   ├── Dockerfile           # Multi-stage hardened Python container
│   └── pyproject.toml       # Backend dependencies & tool configurations
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router (page, layout)
│   │   ├── components/      # UI components (Dashboard, DiffViewer, etc.)
│   │   └── lib/             # Typed API client, storage & interfaces
│   ├── tests/               # Node test runner suite
│   ├── Dockerfile           # Multi-stage optimized Node.js container
│   └── package.json         # Frontend dependencies & scripts
├── docs/                    # Architecture, API, CI/CD, and Demo guides
├── .github/workflows/       # CI (ci.yml) and Release CD (release.yml)
├── docker-compose.yml       # Production orchestration
├── IMPLEMENTATION_PLAN.md   # Detailed implementation plan and test report
└── .env.example             # Documented environment configuration template
```

---

## Quickstart

### Option 1: Docker Compose (Recommended)

```sh
# Start all services (frontend, backend, postgres, ollama)
docker compose up --build
```

- **Frontend UI**: <http://localhost:3000>
- **Backend API & Swagger Docs**: <http://localhost:8000/docs>
- **Health Check**: <http://localhost:8000/health>

### Option 2: Local Development

#### Backend Setup
```sh
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # optional: defaults work out of the box
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup
```sh
cd frontend
npm install
npm run dev
```

---

## Testing & Quality Assurance

```sh
# Backend Test Suite (893 tests)
python3 -m pytest backend/tests

# Static Linting & Formatting Check
python3 -m ruff check backend && python3 -m ruff format --check backend

# Strict Type Checking
python3 -m mypy --config-file backend/pyproject.toml backend/app backend/tests

# Security SAST & Dependency Audits
python3 -m bandit -r backend/app -ll -ii

# Frontend Verification & Production Build
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

---

## License

Licensed under the [Apache License 2.0](LICENSE).
