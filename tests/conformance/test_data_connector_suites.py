"""Honest D1 connectors must pass the reusable conformance suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_factory import FIXED
from speaker_attribution_video.data.conformance import conform_data_connector
from speaker_attribution_video.data.connector import ConnectorRef
from speaker_attribution_video.data.connectors.local import LocalFileConnector
from speaker_attribution_video.data.connectors.synthetic import (
    SyntheticFixtureConnector,
    fixture_digest,
)
from speaker_attribution_video.data.connectors.wav import SyntheticKind, render_fixture
from speaker_attribution_video.data.enums import DataSensitivity, RightsVerification
from speaker_attribution_video.data.rights import RightsRecord

pytestmark = pytest.mark.conformance

_TONE = ConnectorRef(logical_ref="tone", display_name="tone")
_RIGHTS = RightsRecord(verification=RightsVerification.USER_ATTESTED, license_id="caller-attested")


def test_synthetic_connector_conformance() -> None:
    conform_data_connector(
        lambda: SyntheticFixtureConnector(seed=1, duration_ms=100, ingested_at=FIXED),
        _TONE,
        expected_digest=fixture_digest(SyntheticKind.TONE, seed=1, duration_ms=100),
        created_at=FIXED,
    )


def test_local_connector_conformance(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    payload = render_fixture(SyntheticKind.TONE, seed=1, duration_ms=100)
    (root / "tone.wav").write_bytes(payload)
    digest = fixture_digest(SyntheticKind.TONE, seed=1, duration_ms=100)
    conform_data_connector(
        lambda: LocalFileConnector(allowed_root=root, ingested_at=FIXED),
        ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
        rights=_RIGHTS,
        sensitivity=DataSensitivity.INTERNAL,
        expected_digest=digest,
        created_at=FIXED,
    )
