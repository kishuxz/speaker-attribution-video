#!/usr/bin/env python3
"""Local G1 verification (no models, no network downloads)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    run([sys.executable, "scripts/check_public_tree.py"])
    run([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"])
    run([sys.executable, "-m", "pytest", "-q"])
    run(
        [
            sys.executable,
            "-c",
            "from speaker_attribution_video.graph.serialize import assert_schema_drift_free; assert_schema_drift_free(); print('schema-drift-ok')",
        ]
    )
    run(
        [
            sys.executable,
            "-c",
            "from speaker_attribution_video.graph import GRAPH_SCHEMA_VERSION; print(GRAPH_SCHEMA_VERSION)",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
