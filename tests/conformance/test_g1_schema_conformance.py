"""G1 schema conformance smoke. T1E expands backend suites; this is not a placeholder."""

from __future__ import annotations

import pytest

from speaker_attribution_video.graph.serialize import assert_schema_drift_free, load_json_schema
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

pytestmark = pytest.mark.conformance


def test_bundled_schema_matches_python_enums() -> None:
    assert_schema_drift_free()
    schema = load_json_schema()
    assert schema.get("const") is None
    props = schema["properties"]
    assert isinstance(props, dict)
    version = props["schema_version"]
    assert isinstance(version, dict)
    assert version.get("const") == GRAPH_SCHEMA_VERSION
