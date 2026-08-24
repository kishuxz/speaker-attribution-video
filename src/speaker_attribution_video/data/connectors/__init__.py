"""Runtime connectors for D1. Local files and synthetic fixtures only."""

from __future__ import annotations

from speaker_attribution_video.data.connectors.local import LocalFileConnector, safe_logical_name
from speaker_attribution_video.data.connectors.synthetic import (
    SyntheticFixtureConnector,
    fixture_bytes,
    fixture_digest,
)
from speaker_attribution_video.data.connectors.wav import SyntheticKind

__all__ = [
    "LocalFileConnector",
    "SyntheticFixtureConnector",
    "SyntheticKind",
    "fixture_bytes",
    "fixture_digest",
    "safe_logical_name",
]
