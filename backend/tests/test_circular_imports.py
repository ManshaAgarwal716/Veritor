"""Regression test suite for circular imports across Veritor modules.

Circular imports can remain hidden when modules are imported in a specific order during
tests, but fail when a fresh Python process or container entrypoint imports them in
isolation (e.g., Docker container startup with uvicorn).
"""

import subprocess
import sys
from pathlib import Path


def _run_isolated_import(module_name: str) -> subprocess.CompletedProcess[str]:
    """Execute python in a fresh child process to test importing a module without cache."""
    # Ensure backend directory is in PYTHONPATH so fresh process resolves app.*
    backend_dir = str(Path(__file__).resolve().parent.parent)
    code = f"import sys; sys.path.insert(0, {backend_dir!r}); import {module_name}"
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )


def test_import_ai_investigator_in_fresh_process() -> None:
    """Importing app.ai.investigator must not raise circular import errors with app.analysis."""
    res = _run_isolated_import("app.ai.investigator")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_import_analysis_service_in_fresh_process() -> None:
    """Importing app.analysis.service must not raise circular import errors."""
    res = _run_isolated_import("app.analysis.service")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_import_analysis_package_in_fresh_process() -> None:
    """Importing app.analysis root package must not trigger circular dependencies."""
    res = _run_isolated_import("app.analysis")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_import_docker_entrypoint_main_in_fresh_process() -> None:
    """Importing app.main (used by Docker uvicorn command) must succeed cleanly."""
    res = _run_isolated_import("app.main")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_import_related_submodules_in_fresh_processes() -> None:
    """Verify that all AI, analysis, and scan orchestration modules import cleanly."""
    modules_to_test = [
        "app.ai.client",
        "app.ai.models",
        "app.ai.investigator",
        "app.analysis.models",
        "app.analysis.analyzer",
        "app.analysis.service",
        "app.scans.pipeline",
        "app.scans.manager",
        "app.main",
    ]
    for mod in modules_to_test:
        res = _run_isolated_import(mod)
        assert res.returncode == 0, (
            f"Failed importing {mod} in fresh process.\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )


def test_analyze_release_runtime_annotations() -> None:
    """Verify that ReleaseAnalysis and analyze_release preserve types and runtime behavior."""
    from app.analysis.service import ReleaseAnalysis, analyze_release

    assert callable(analyze_release)
    # Check that annotations reflect the expected signatures
    annotations = analyze_release.__annotations__
    assert "ai_investigator" in annotations
    assert annotations["ai_investigator"] == "AIInvestigator | None"
    assert annotations["return"] in ("ReleaseAnalysis", ReleaseAnalysis)
