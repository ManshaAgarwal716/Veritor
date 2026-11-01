# HACKATHON.md

## Team Name
CommitCrew

## Team Members
1. Yashasvee Singh
2. Mansha Agarwal
3. Siddhi Varshney
4. Komal

## Selected Problem Statement
**Problem 04: Published Package vs Source Code Integrity Analyzer**

## Solution Overview
**Veritor** is an automated software supply chain integrity platform that compares published packages on **npm** and **PyPI** with their upstream source code repositories on GitHub. It detects unauthorized modifications, deceptive build artifacts, manifest spoofing, and supply chain attacks without ever executing untrusted code.

For complete documentation, see:
- [System Architecture](docs/architecture.md)
- [REST API Reference](docs/api.md)
- [Hackathon Demonstration Guide](docs/demo.md)
- [CI/CD & Security Architecture](docs/CI-CD.md)
- [Full Implementation Plan & Report](IMPLEMENTATION_PLAN.md)

---

## AI Models Used

### 1. Qwen2.5-Coder 7B (`qwen2.5-coder:7b`, via Ollama)
- **Role**: AI Behavioral Investigator.
- **Reason**: Specialized code intelligence model running locally on consumer hardware (fits comfortably on 16 GB laptop).
- **Function**: Explains what flagged code changes do, contextualizes differences, and synthesizes behavioral explanations.
- **Guardrail**: Pydantic validated output. Prohibited from overriding deterministic risk results, clearing hard findings, or inventing unsupported claims.

### 2. Phi-4 Mini (`phi4-mini`, via Ollama)
- **Role**: Lightweight finding triage and priority ranking.
- **Reason**: Fast open-weight model capable of fast multi-finding urgency ranking.

---

## Safety Invariants & Principles

1. **Evidence First**: Static AST analysis (Tree-Sitter) produces deterministic findings before models are invoked.
2. **Models Cannot Clear Hard Evidence**: An AI model may not downgrade or dismiss hard findings (such as an untracked install script or dynamic eval execution).
3. **Zero Untrusted Execution**: Package contents are untrusted data. They are never installed, executed, or imported.
4. **All Processing Runs Locally**: Works completely offline. Ollama runs locally; PostgreSQL falls back to in-memory mode when credentials are absent.
5. **Rigorous Provenance**: Sigstore and PEP 740 digital attestations are cryptographically validated. Missing provenance awards 0 risk points and does not falsely imply maliciousness.

---

## Hackathon Demonstration Workflow

1. **Start the Platform**: Run `docker compose up --build` or launch backend on `:8000` and frontend on `:3000`.
2. **Scan Legitimate Package**: Click `chalk@5.3.0` on the landing page. Observe compiler build output recognition (`LIKELY_GENERATED`), verified SLSA provenance, and 0/100 `LOW` risk.
3. **Scan PyPI Package**: Select PyPI, enter `requests@2.31.0`. Observe binary wheel `.whl` safe extraction, Python AST analysis, and clean risk score.
4. **Inspect Simulated Attack**: Run `pytest backend/tests/test_scenario_verifications.py -v`. Observe detection of injected install scripts with dynamic evaluation (`eval`), base64 decoding, subprocess spawning, and automatic `CRITICAL` risk escalation.
5. **Release Evolution Monitoring**: View the **Watchlist**, click **Check for Updates**, and inspect the release-to-release score delta and file diff breakdown on the report dashboard.
6. **Download Reports**: Click **Export JSON** (cryptographic SHA-256 hash) or **Export PDF** (executive ReportLab cybersecurity report).
