"""Collection anti-vacuity: core suites must stay collected and skip-free."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIN_UNIT = 70
MIN_PROPERTY = 10
MIN_CONFORMANCE = 15


def _collect(marker: str) -> tuple[int, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            marker,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    # pytest uses exit status 5 when a marker selects nothing.
    if completed.returncode not in {0, 5}:
        raise AssertionError(f"collection failed for {marker!r}:\n{output}")
    collected = [
        line
        for line in completed.stdout.splitlines()
        if line.strip() and not line.startswith("=") and "tests collected" not in line
    ]
    # pytest -q --collect-only prints one node id per line, then a summary.
    nodes = [line for line in collected if "::" in line]
    return len(nodes), output


def test_no_collection_errors_and_nonzero_core_groups() -> None:
    unit_n, unit_out = _collect("unit")
    property_n, property_out = _collect("property")
    conformance_n, conformance_out = _collect("conformance")
    assert unit_n >= MIN_UNIT, unit_out
    assert property_n >= MIN_PROPERTY, property_out
    assert conformance_n >= MIN_CONFORMANCE, conformance_out
    for label, text in (
        ("unit", unit_out),
        ("property", property_out),
        ("conformance", conformance_out),
    ):
        assert "error during collection" not in text.lower(), label
        assert "skipped" not in text.lower() or "0 skipped" in text.lower()


def test_optional_markers_have_no_empty_placeholder_tests() -> None:
    for marker in ("integration", "model", "gpu"):
        count, output = _collect(marker)
        assert count == 0, f"{marker} tests must not exist as T1 placeholders:\n{output}"
