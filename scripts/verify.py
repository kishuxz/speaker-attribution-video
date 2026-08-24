#!/usr/bin/env python3
"""Cross-platform verification entry point for T1 quality gates.

Runs the documented sequence and stops on the first failure, preserving the
failing command and its exit code. Never downloads models or datasets, never
requires credentials, never starts Docker, and never calls paid APIs.

Python 3.11 is the only supported runtime. Any other interpreter is an
environment mismatch, not a product failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = (3, 11)

STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("public-tree-scan", ("scripts/check_public_tree.py",)),
    ("source-compile", ("-m", "compileall", "-q", "src", "tests", "scripts")),
    ("ruff-format", ("-m", "ruff", "format", "--check", "src", "tests", "scripts")),
    ("ruff-lint", ("-m", "ruff", "check", "src", "tests", "scripts")),
    ("mypy", ("-m", "mypy", "src")),
    ("unit-tests", ("-m", "pytest", "-q", "-m", "unit")),
    ("property-tests", ("-m", "pytest", "-q", "-m", "property")),
    ("conformance-tests", ("-m", "pytest", "-q", "-m", "conformance")),
    (
        "coverage-check",
        (
            "-m",
            "pytest",
            "-q",
            "-m",
            "unit or property or conformance",
            "--cov=speaker_attribution_video",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
        ),
    ),
    ("coverage-graph-core", ("scripts/check_coverage_policy.py",)),
    (
        "json-schema-drift",
        (
            "-c",
            "from speaker_attribution_video.graph.serialize import assert_schema_drift_free; "
            "assert_schema_drift_free(); print('schema-drift-ok')",
        ),
    ),
)


class StepFailure(SystemExit):
    """Nonzero exit that preserves the failed command."""


def require_python_311(version_info: tuple[int, ...] = sys.version_info) -> None:
    if version_info[:2] != SUPPORTED:
        current = ".".join(str(part) for part in version_info[:3])
        raise StepFailure(
            "Python 3.11 is the only supported runtime. "
            f"This interpreter is {current}. "
            "This is an environment mismatch, not a product failure."
        )


def format_command(cmd: list[str]) -> str:
    return " ".join(cmd)


def run_step(
    name: str, cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> None:
    print(f"==> {name}")
    print("+", format_command(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        print(
            f"FAILED step={name!r} exit={completed.returncode} cmd={format_command(cmd)!r}",
            flush=True,
        )
        raise StepFailure(completed.returncode)


def python_cmd(*args: str) -> list[str]:
    return [sys.executable, *args]


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def package_build() -> Path:
    dist = ROOT / "dist"
    if dist.exists():
        for leftover in dist.iterdir():
            leftover.unlink()
    run_step("package-build", python_cmd("-m", "build", "--sdist", "--wheel"))
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if not wheels or not sdists:
        print("FAILED step='package-build' exit=1 cmd='missing dist artifacts'", flush=True)
        raise StepFailure(1)
    return wheels[-1]


def wheel_metadata_check() -> None:
    artifacts = sorted((ROOT / "dist").iterdir())
    run_step(
        "wheel-metadata",
        python_cmd("-m", "twine", "check", *[str(path) for path in artifacts]),
    )


def clean_wheel_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sav-wheel-") as raw:
        venv_dir = Path(raw) / "venv"
        print("==> clean-wheel-install", flush=True)
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(venv_dir)
        py = venv_python(venv_dir)
        isolated_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONNOUSERSITE": "1",
        }
        run_step(
            "clean-wheel-install",
            [str(py), "-m", "pip", "install", "--no-deps", str(wheel)],
            env=isolated_env,
        )
        run_step(
            "clean-wheel-import",
            [
                str(py),
                "-c",
                "from speaker_attribution_video import __version__; "
                "from speaker_attribution_video.cli import main; "
                "from speaker_attribution_video.graph import GRAPH_SCHEMA_VERSION, TimeSpan; "
                "assert __version__; TimeSpan(0, 1); print(__version__, GRAPH_SCHEMA_VERSION)",
            ],
            env=isolated_env,
        )
        run_step(
            "clean-wheel-cli",
            [str(py), "-m", "speaker_attribution_video", "--help"],
            env=isolated_env,
        )


def dependency_audit() -> None:
    run_step(
        "dependency-audit",
        python_cmd(
            "-m",
            "pip_audit",
            "--progress-spinner",
            "off",
            "--requirement",
            "requirements-dev.lock",
        ),
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        require_python_311()
        os.chdir(ROOT)
        for name, args in STEPS:
            run_step(name, python_cmd(*args))
        wheel = package_build()
        wheel_metadata_check()
        clean_wheel_install(wheel)
        dependency_audit()
    except StepFailure as exc:
        code = exc.code
        if isinstance(code, str):
            print(code, flush=True)
            return 2
        return int(code) if code else 1
    print("verify: all gates passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
