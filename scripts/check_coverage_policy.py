#!/usr/bin/env python3
"""Enforce T1H coverage gates after pytest-cov has written .coverage.

Coverage is evidence of execution, not correctness. This script does not
claim model accuracy, graph semantic validity, or that untested branches
are safe. It only checks that the recorded line-coverage floors were met.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from coverage import Coverage

ROOT = Path(__file__).resolve().parents[1]
OVERALL_MIN = 90
GRAPH_MIN = 95
GRAPH_INCLUDE = ["*/speaker_attribution_video/graph/*", "src/speaker_attribution_video/graph/*"]


def _percent(cov: Coverage, include: list[str] | None = None) -> float:
    buf = StringIO()
    if include is None:
        return float(cov.report(file=buf, show_missing=True))
    return float(cov.report(file=buf, show_missing=True, include=include))


def main() -> int:
    data = ROOT / ".coverage"
    if not data.exists():
        print("FAILED: .coverage is missing; run pytest --cov first", flush=True)
        return 1
    cov = Coverage(data_file=str(data))
    cov.load()
    overall = _percent(cov)
    graph = _percent(cov, include=GRAPH_INCLUDE)
    print(f"coverage-policy overall_line={overall:.2f}% min={OVERALL_MIN}")
    print(f"coverage-policy graph_line={graph:.2f}% min={GRAPH_MIN}")
    print("coverage-policy: coverage is evidence of execution, not correctness")
    failed = False
    if overall < OVERALL_MIN:
        print(f"FAILED: overall line coverage {overall:.2f}% < {OVERALL_MIN}%", flush=True)
        failed = True
    if graph < GRAPH_MIN:
        print(
            f"FAILED: graph/validation core line coverage {graph:.2f}% < {GRAPH_MIN}%",
            flush=True,
        )
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
