"""Pytest configuration: markers, Hypothesis profiles, no empty core suites."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import settings

settings.register_profile(
    "ci",
    max_examples=40,
    deadline=500,
    print_blob=True,
    derandomize=False,
)
settings.load_profile("ci")

CORE_MARKERS = frozenset({"unit", "property", "conformance"})
OPTIONAL_MARKERS = frozenset({"integration", "model", "gpu", "slow"})


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = Path(str(item.fspath)).as_posix()
        names = {marker.name for marker in item.iter_markers()}
        if "/tests/property/" in path or path.endswith("/tests/property"):
            if "property" not in names:
                item.add_marker(pytest.mark.property)
        elif "/tests/conformance/" in path or path.endswith("/tests/conformance"):
            if "conformance" not in names:
                item.add_marker(pytest.mark.conformance)
        elif not (names & (CORE_MARKERS | OPTIONAL_MARKERS)):
            item.add_marker(pytest.mark.unit)
