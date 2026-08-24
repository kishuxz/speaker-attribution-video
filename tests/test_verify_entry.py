"""Unit tests for the T1 verification entry point and marker taxonomy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify.py"


def _load_verify() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sav_verify", VERIFY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_require_python_311_accepts_311() -> None:
    verify = _load_verify()
    verify.require_python_311((3, 11, 16, "final", 0))


def test_require_python_311_rejects_314_as_environment_mismatch() -> None:
    verify = _load_verify()
    with pytest.raises(verify.StepFailure) as exc:
        verify.require_python_311((3, 14, 0, "final", 0))
    message = str(exc.value)
    assert "environment mismatch" in message
    assert "3.14" in message
    assert "product failure" in message


def test_verify_step_order_is_stable() -> None:
    verify = _load_verify()
    names = [name for name, _args in verify.STEPS]
    assert names == [
        "public-tree-scan",
        "source-compile",
        "ruff-format",
        "ruff-lint",
        "mypy",
        "unit-tests",
        "property-tests",
        "conformance-tests",
        "coverage-check",
        "coverage-graph-core",
        "json-schema-drift",
        "data-manifest-schema-drift",
    ]


def test_verify_jobs_cover_documented_steps() -> None:
    verify = _load_verify()
    union = set()
    for names in verify.JOB_STEPS.values():
        union.update(names)
    step_names = {name for name, _args in verify.STEPS}
    assert step_names <= union
    assert verify.parse_jobs([]) == frozenset(verify.JOB_NAMES)
    assert verify.parse_jobs(["--job", "quality"]) == frozenset({"quality"})


def test_inspect_wheel_requires_schema_and_excludes_tests(tmp_path: Path) -> None:
    import zipfile

    verify = _load_verify()
    wheel = tmp_path / "demo.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("speaker_attribution_video/py.typed", "")
        archive.writestr("speaker_attribution_video/graph/schemas/evidence_graph.g1.v1.json", "{}")
        archive.writestr("speaker_attribution_video/data/schemas/media_manifest.d1.v1.json", "{}")
        archive.writestr("speaker_attribution_video/cli.py", "x=1\n")
    verify.inspect_wheel(wheel)
    bad = tmp_path / "bad.whl"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("speaker_attribution_video/py.typed", "")
        archive.writestr("speaker_attribution_video/graph/schemas/evidence_graph.g1.v1.json", "{}")
        archive.writestr("speaker_attribution_video/data/schemas/media_manifest.d1.v1.json", "{}")
        archive.writestr("tests/secret.py", "assert False\n")
    with pytest.raises(verify.StepFailure):
        verify.inspect_wheel(bad)


def test_run_step_preserves_nonzero_exit(tmp_path: Path) -> None:
    verify = _load_verify()
    with pytest.raises(verify.StepFailure) as exc:
        verify.run_step(
            "intentional-failure",
            [verify.sys.executable, "-c", "raise SystemExit(7)"],
            cwd=tmp_path,
        )
    assert exc.value.code == 7
