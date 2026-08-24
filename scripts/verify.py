#!/usr/bin/env python3
"""Cross-platform verification entry point for T1 quality gates.

Runs the documented sequence and stops on the first failure, preserving the
failing command and its exit code. Never downloads models or datasets, never
requires credentials, never starts Docker, and never calls paid APIs.

Python 3.11 is the only supported runtime. Any other interpreter is an
environment mismatch, not a product failure.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = (3, 11)
JOB_NAMES = ("quality", "tests", "package", "security-public-tree")
REQUIRED_WHEEL_PATHS = (
    "speaker_attribution_video/py.typed",
    "speaker_attribution_video/graph/schemas/evidence_graph.g1.v1.json",
)
FORBIDDEN_ARCHIVE_PREFIXES = (
    "tests/",
    "scripts/",
    ".github/",
    "requirements/",
    "docs/",
    ".hypothesis/",
    ".pytest_cache/",
)
FORBIDDEN_ARCHIVE_NAMES = frozenset({".coverage", "coverage.xml", "junit.xml", ".env"})
JOB_STEPS: dict[str, frozenset[str]] = {
    "quality": frozenset({"source-compile", "ruff-format", "ruff-lint", "mypy"}),
    "tests": frozenset(
        {
            "unit-tests",
            "property-tests",
            "conformance-tests",
            "coverage-check",
            "coverage-graph-core",
            "json-schema-drift",
        }
    ),
    "package": frozenset(
        {
            "package-build",
            "inspect-package",
            "wheel-metadata",
            "clean-wheel-install",
        }
    ),
    "security-public-tree": frozenset({"public-tree-scan", "dependency-audit"}),
}

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
            "--cov-report=xml:coverage.xml",
            "--junitxml=junit.xml",
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


def parse_jobs(argv: list[str] | None) -> frozenset[str]:
    parser = argparse.ArgumentParser(prog="verify.py")
    parser.add_argument(
        "--job",
        action="append",
        choices=JOB_NAMES,
        dest="jobs",
        help="Run one focused CI job. Repeatable. Default: all jobs in documented order.",
    )
    args = parser.parse_args(argv)
    if not args.jobs:
        return frozenset(JOB_NAMES)
    return frozenset(args.jobs)


def selected_step_names(jobs: frozenset[str]) -> frozenset[str]:
    names: set[str] = set()
    for job in jobs:
        names.update(JOB_STEPS[job])
    return frozenset(names)


def _archive_relative(name: str) -> str:
    normalized = name.replace("\\", "/")
    parts = normalized.split("/", 1)
    if len(parts) == 2 and parts[0].startswith("speaker_attribution_video-"):
        return parts[1]
    return normalized


def _forbidden_member(name: str) -> str | None:
    relative = _archive_relative(name)
    if Path(relative).name in FORBIDDEN_ARCHIVE_NAMES:
        return Path(relative).name
    first = relative.split("/", 1)[0]
    forbidden_roots = {prefix.rstrip("/") for prefix in FORBIDDEN_ARCHIVE_PREFIXES}
    if first in forbidden_roots:
        return first
    return None


def inspect_wheel(wheel: Path) -> None:
    print("==> inspect-package", flush=True)
    with zipfile.ZipFile(wheel) as archive:
        names = [
            info.filename.replace("\\", "/") for info in archive.infolist() if not info.is_dir()
        ]
    missing = [path for path in REQUIRED_WHEEL_PATHS if path not in names]
    if missing:
        print(
            f"FAILED step='inspect-package' exit=1 cmd='missing wheel paths {missing}'",
            flush=True,
        )
        raise StepFailure(1)
    forbidden = [name for name in names if _forbidden_member(name)]
    if forbidden:
        print(
            f"FAILED step='inspect-package' exit=1 cmd='forbidden wheel paths {forbidden[:8]}'",
            flush=True,
        )
        raise StepFailure(1)
    print(f"inspect-package wheel members={len(names)} required=ok excluded=ok", flush=True)


def inspect_sdist(sdist: Path) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = [
            member.name.replace("\\", "/") for member in archive.getmembers() if member.isfile()
        ]
    forbidden = [name for name in names if _forbidden_member(name)]
    if forbidden:
        print(
            f"FAILED step='inspect-package' exit=1 cmd='forbidden sdist paths {forbidden[:8]}'",
            flush=True,
        )
        raise StepFailure(1)
    if not any(name.endswith("graph/schemas/evidence_graph.g1.v1.json") for name in names):
        print("FAILED step='inspect-package' exit=1 cmd='sdist missing JSON Schema'", flush=True)
        raise StepFailure(1)
    if not any(name.endswith("py.typed") for name in names):
        print("FAILED step='inspect-package' exit=1 cmd='sdist missing py.typed'", flush=True)
        raise StepFailure(1)
    print(f"inspect-package sdist members={len(names)} required=ok excluded=ok", flush=True)


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
                "import pathlib; "
                "import speaker_attribution_video; "
                "import speaker_attribution_video.backends; "
                "import speaker_attribution_video.cli; "
                "import speaker_attribution_video.graph; "
                "import speaker_attribution_video.integrations; "
                "from speaker_attribution_video import __version__; "
                "from speaker_attribution_video.cli import main; "
                "from speaker_attribution_video.graph import GRAPH_SCHEMA_VERSION, TimeSpan; "
                "from speaker_attribution_video.graph.time import TimeSpan as TS; "
                "path = pathlib.Path(speaker_attribution_video.__file__).resolve(); "
                "assert 'site-packages' in path.parts, path; "
                "assert __version__; TS(0, 1); "
                "print(__version__, GRAPH_SCHEMA_VERSION, path)",
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
    try:
        require_python_311()
        os.chdir(ROOT)
        jobs = parse_jobs(argv)
        selected = selected_step_names(jobs)
        print(f"verify jobs={','.join(sorted(jobs))}", flush=True)
        for name, args in STEPS:
            if name in selected:
                run_step(name, python_cmd(*args))
        if "package-build" in selected:
            wheel = package_build()
            sdists = sorted((ROOT / "dist").glob("*.tar.gz"))
            if "inspect-package" in selected:
                inspect_wheel(wheel)
                if sdists:
                    inspect_sdist(sdists[-1])
            if "wheel-metadata" in selected:
                wheel_metadata_check()
            if "clean-wheel-install" in selected:
                clean_wheel_install(wheel)
        if "dependency-audit" in selected:
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
    raise SystemExit(main(sys.argv[1:]))
