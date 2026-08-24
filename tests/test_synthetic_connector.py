"""Unit tests for the synthetic fixture connector."""

from __future__ import annotations

import pytest

from data_factory import FIXED, JOB, NS
from speaker_attribution_video.backends.contracts import CancellationToken, RequestContext
from speaker_attribution_video.data.connector import (
    ConnectorError,
    ConnectorRef,
    IngestRequest,
    InspectRequest,
    ValidateRequest,
)
from speaker_attribution_video.data.connectors.synthetic import (
    SyntheticFixtureConnector,
    fixture_digest,
)
from speaker_attribution_video.data.connectors.wav import SyntheticKind
from speaker_attribution_video.data.enums import (
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    IngestionState,
    SourceType,
)
from speaker_attribution_video.data.versions import CONNECTOR_INPUT_SCHEMA_VERSION

pytestmark = pytest.mark.unit


def _ctx() -> RequestContext:
    return RequestContext(
        namespace_id=NS, job_id=JOB, input_schema_version=CONNECTOR_INPUT_SCHEMA_VERSION
    )


def test_synthetic_fixtures_are_deterministic_and_labelled() -> None:
    connector = SyntheticFixtureConnector(seed=1, duration_ms=100, ingested_at=FIXED)
    result = connector.ingest(
        IngestRequest(
            context=_ctx(),
            targets=(ConnectorRef(logical_ref="tone", display_name="tone"),),
        )
    )
    assert result.state is IngestionState.ACCEPTED
    manifest = result.manifests[0]
    assert manifest.source.source_type is SourceType.SYNTHETIC
    assert manifest.sensitivity is DataSensitivity.SYNTHETIC
    assert manifest.content_sha256 == fixture_digest(SyntheticKind.TONE, seed=1, duration_ms=100)
    again = SyntheticFixtureConnector(seed=1, duration_ms=100, ingested_at=FIXED).inspect(
        InspectRequest(
            context=_ctx(),
            target=ConnectorRef(logical_ref="tone", display_name="tone"),
        )
    )
    assert again.manifests[0].content_sha256 == manifest.content_sha256
    assert again.manifests[0].manifest_id == manifest.manifest_id


def test_silence_noise_and_transcript_text_fixtures() -> None:
    connector = SyntheticFixtureConnector(seed=7, duration_ms=100, ingested_at=FIXED)
    for name, kind in (
        ("silence", SyntheticKind.SILENCE),
        ("noise", SyntheticKind.NOISE),
        ("transcript-text", SyntheticKind.TRANSCRIPT_TEXT),
    ):
        result = connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref=name, display_name=name),
            )
        )
        assert result.manifests[0].content_sha256 == fixture_digest(kind, seed=7, duration_ms=100)
        assert result.manifests[0].source.source_type is SourceType.SYNTHETIC
    transcript = connector.inspect(
        InspectRequest(
            context=_ctx(),
            target=ConnectorRef(logical_ref="transcript-text", display_name="transcript-text"),
        )
    )
    assert "speaker-alpha-synthetic-sentence-one" in (
        transcript.manifests[0].source.to_dict().get("provenance_notes") or ""
    )
    assert "celebrity" not in str(transcript.manifests[0].to_dict()).lower()


def test_synthetic_rejects_unknown_fixture_and_local_files_capability() -> None:
    connector = SyntheticFixtureConnector(ingested_at=FIXED)
    with pytest.raises(ConnectorError) as unknown:
        connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="celebrity-voice", display_name="x"),
            )
        )
    assert unknown.value.reason is ConnectorFailureReason.INVALID_INPUT
    with pytest.raises(ConnectorError) as cap:
        connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone", display_name="tone"),
                requested_capabilities=frozenset({ConnectorCapability.LOCAL_FILES}),
            )
        )
    assert cap.value.reason is ConnectorFailureReason.UNSUPPORTED_CAPABILITY
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ConnectorError) as cancelled:
        connector.validate(
            ValidateRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone", display_name="tone"),
            ),
            cancel=token,
        )
    assert cancelled.value.reason is ConnectorFailureReason.CANCELLATION
    connector.close()
