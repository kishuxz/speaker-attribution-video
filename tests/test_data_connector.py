"""Unit tests for the source-neutral DataConnector protocol."""

from __future__ import annotations

import pytest

from data_factory import FIXED, HASH, JOB, NS, synthetic_manifest, synthetic_snapshot_entry
from speaker_attribution_video.backends.contracts import CancellationToken, RequestContext
from speaker_attribution_video.data.connector import (
    ConnectorCapabilities,
    ConnectorError,
    ConnectorIdentity,
    ConnectorRef,
    ConnectorResult,
    DataConnector,
    IngestRequest,
    InspectRequest,
    ValidateRequest,
    require_connector_capabilities,
    require_input_schema,
)
from speaker_attribution_video.data.enums import (
    ConnectorCapability,
    ConnectorFailureReason,
    IngestionState,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.snapshot import make_ingestion_snapshot
from speaker_attribution_video.data.versions import CONNECTOR_INPUT_SCHEMA_VERSION

pytestmark = pytest.mark.unit


class _RecordingConnector:
    def __init__(self) -> None:
        self.closed = False
        self._identity = ConnectorIdentity(
            name="recording-connector",
            version="0.1.0",
            configuration_fingerprint=HASH,
        )
        self._caps = ConnectorCapabilities(
            synthetic_generation=True,
            checksum_verification=True,
            immutable_snapshots=True,
            rights_metadata=True,
            sensitivity_enforcement=True,
        )

    def identity(self) -> ConnectorIdentity:
        return self._identity

    def capabilities(self) -> ConnectorCapabilities:
        return self._caps

    def _guard(
        self,
        requested: frozenset[ConnectorCapability],
        cancel: CancellationToken | None,
    ) -> None:
        require_connector_capabilities(self._caps, requested)
        if cancel is not None and cancel.is_cancelled():
            raise ConnectorError(ConnectorFailureReason.CANCELLATION, "cancelled")

    def _result(self, state: IngestionState) -> ConnectorResult:
        snapshot = make_ingestion_snapshot(
            namespace_id=NS,
            job_id=JOB,
            entries=(synthetic_snapshot_entry(state=state),),
            connector_name=self._identity.name,
            connector_version=self._identity.version,
            created_at=FIXED,
        )
        return ConnectorResult(
            state=snapshot.state,
            identity=self._identity,
            output_schema_version=self._identity.output_schema_version,
            snapshot=snapshot,
            manifests=(synthetic_manifest(),) if state is IngestionState.ACCEPTED else (),
        )

    def validate(
        self, request: ValidateRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        self._guard(request.requested_capabilities, cancel)
        return self._result(IngestionState.ACCEPTED)

    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        self._guard(request.requested_capabilities, cancel)
        return self._result(IngestionState.ACCEPTED)

    def ingest(
        self, request: IngestRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        self._guard(request.requested_capabilities, cancel)
        return self._result(IngestionState.ACCEPTED)

    def close(self) -> None:
        self.closed = True


def _context() -> RequestContext:
    return RequestContext(namespace_id=NS, job_id=JOB)


def test_recording_connector_satisfies_protocol() -> None:
    connector: DataConnector = _RecordingConnector()
    assert isinstance(connector, DataConnector)
    ref = ConnectorRef(
        logical_ref="artifact://synth.example/sources/tone-01", display_name="tone-01"
    )
    result = connector.ingest(IngestRequest(context=_context(), targets=(ref,)))
    assert result.state is IngestionState.ACCEPTED
    assert result.snapshot is not None
    connector.close()
    assert isinstance(connector, _RecordingConnector)
    assert connector.closed is True


def test_unsupported_capability_is_a_typed_rejection() -> None:
    connector = _RecordingConnector()
    with pytest.raises(ConnectorError) as exc:
        connector.inspect(
            InspectRequest(
                context=_context(),
                target=ConnectorRef(
                    logical_ref="artifact://synth.example/sources/tone-01",
                    display_name="tone-01",
                ),
                requested_capabilities=frozenset({ConnectorCapability.LOCAL_FILES}),
            )
        )
    assert exc.value.reason is ConnectorFailureReason.UNSUPPORTED_CAPABILITY
    assert "/" not in str(exc.value.details.get("capabilities", ""))


def test_cancellation_and_schema_mismatch() -> None:
    connector = _RecordingConnector()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ConnectorError) as cancelled:
        connector.validate(
            ValidateRequest(
                context=_context(),
                target=ConnectorRef(
                    logical_ref="artifact://synth.example/sources/tone-01",
                    display_name="tone-01",
                ),
            ),
            cancel=token,
        )
    assert cancelled.value.reason is ConnectorFailureReason.CANCELLATION
    with pytest.raises(ConnectorError) as schema:
        require_input_schema("d1.connector.input.v0")
    assert schema.value.reason is ConnectorFailureReason.SCHEMA_MISMATCH
    assert require_input_schema(CONNECTOR_INPUT_SCHEMA_VERSION) == CONNECTOR_INPUT_SCHEMA_VERSION


def test_accepted_result_cannot_hide_partial_or_failure() -> None:
    identity = ConnectorIdentity(
        name="recording-connector",
        version="0.1.0",
        configuration_fingerprint=HASH,
    )
    with pytest.raises(DataContractError):
        ConnectorResult(
            state=IngestionState.ACCEPTED,
            identity=identity,
            output_schema_version=identity.output_schema_version,
        )
    partial = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(
            synthetic_snapshot_entry(),
            synthetic_snapshot_entry(
                content_sha256="b" * 64,
                logical_filename="synthetic-tone-02.wav",
                state=IngestionState.REJECTED,
            ),
        ),
        connector_name="recording-connector",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    with pytest.raises(DataContractError):
        ConnectorResult(
            state=IngestionState.ACCEPTED,
            identity=identity,
            output_schema_version=identity.output_schema_version,
            snapshot=partial,
        )


def test_errors_do_not_leak_filesystem_paths() -> None:
    err = ConnectorError(
        ConnectorFailureReason.PATH_ESCAPE,
        "path is outside the allowed root",
        details={"path": "/Users/example/secret.wav", "filename": "secret.wav"},
    )
    assert "/Users" not in str(err)
    assert "secret.wav" not in str(err.details["path"])
    assert err.details["filename"] == "<redacted>"
