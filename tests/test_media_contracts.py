"""Unit tests for MP1 toolchain contracts. No FFmpeg required."""

from __future__ import annotations

import pytest

from data_factory import HASH, JOB, NS, synthetic_manifest
from speaker_attribution_video.backends.contracts import RequestContext
from speaker_attribution_video.media.contracts import (
    InspectedStream,
    MediaInspectionRequest,
    MediaInspectionResult,
    NormalizationRequest,
    NormalizationResult,
    ToolExecutionResult,
)
from speaker_attribution_video.media.enums import (
    CaptureStatus,
    MediaStepState,
    StreamKind,
    StreamSelectionReason,
    ToolCapability,
    ToolLogicalName,
)
from speaker_attribution_video.media.errors import MediaContractError, ToolError
from speaker_attribution_video.media.identity import (
    MediaToolIdentity,
    fingerprint_toolchain,
    parse_tool_version_line,
)
from speaker_attribution_video.media.policy import SubprocessPolicy
from speaker_attribution_video.media.versions import (
    INSPECTION_INPUT_SCHEMA_VERSION,
    INSPECTION_SCHEMA_VERSION,
    NORMALIZATION_INPUT_SCHEMA_VERSION,
    NORMALIZATION_SCHEMA_VERSION,
    SUBPROCESS_POLICY_VERSION,
)

pytestmark = pytest.mark.unit

_VERSION_SHA = "b" * 64


def _ctx() -> RequestContext:
    return RequestContext(namespace_id=NS, job_id=JOB)


def _ffmpeg() -> MediaToolIdentity:
    return MediaToolIdentity(
        logical_name=ToolLogicalName.FFMPEG,
        version="8.0.1",
        version_sha256=_VERSION_SHA,
        capabilities=frozenset({ToolCapability.NORMALIZE_PCM_WAV, ToolCapability.EXTRACT_AUDIO}),
    )


def _ffprobe() -> MediaToolIdentity:
    return MediaToolIdentity(
        logical_name=ToolLogicalName.FFPROBE,
        version="8.0.1",
        version_sha256=_VERSION_SHA,
        capabilities=frozenset({ToolCapability.INSPECT_CONTAINER}),
    )


def test_version_line_parsing_and_identity_are_canonical() -> None:
    version = parse_tool_version_line(
        "ffmpeg", "ffmpeg version 8.0.1 Copyright (c) 2000-2025 the FFmpeg developers"
    )
    assert version == "8.0.1"
    first = _ffmpeg()
    second = MediaToolIdentity.from_dict(first.to_dict())
    assert first == second
    assert "path" not in first.to_dict()
    assert "/" not in str(first.to_dict())


def test_toolchain_fingerprint_is_stable_and_omits_paths() -> None:
    first = fingerprint_toolchain(
        ffmpeg=_ffmpeg(), ffprobe=_ffprobe(), policy_version=SUBPROCESS_POLICY_VERSION
    )
    second = fingerprint_toolchain(
        ffmpeg=_ffmpeg(), ffprobe=_ffprobe(), policy_version=SUBPROCESS_POLICY_VERSION
    )
    assert first.digest == second.digest
    encoded = str(first.to_dict())
    assert "/opt/" not in encoded
    assert "/usr/" not in encoded
    assert "home" not in encoded


def test_subprocess_policy_rejects_unbounded_limits() -> None:
    with pytest.raises(MediaContractError) as exc:
        SubprocessPolicy(max_launch_retries=4)
    assert exc.value.code == "subprocess.retry"
    with pytest.raises(MediaContractError):
        SubprocessPolicy(timeout_ms=0)


def test_tool_execution_result_omits_stdio_contents() -> None:
    result = ToolExecutionResult(
        logical_name=ToolLogicalName.FFPROBE,
        policy_version=SUBPROCESS_POLICY_VERSION,
        duration_us=12,
        exit_status=0,
        stdout_status=CaptureStatus.COMPLETE,
        stderr_status=CaptureStatus.EMPTY,
        stdout_bytes=32,
        stderr_bytes=0,
        stdout_sha256="c" * 64,
        stderr_sha256=None,
        timed_out=False,
        cancelled=False,
        launch_attempts=1,
    )
    payload = result.identity_dict()
    assert "stdout" not in payload
    assert "stderr" not in payload
    assert "argv" not in payload
    assert payload["stdout_sha256"] == "c" * 64


def test_inspection_request_preserves_namespace_and_rejects_paths() -> None:
    manifest = synthetic_manifest()
    request = MediaInspectionRequest(
        context=_ctx(),
        source_manifest=manifest,
        source_relative_ref="tone.wav",
        expected_sha256=HASH,
        input_schema_version=INSPECTION_INPUT_SCHEMA_VERSION,
    )
    assert request.source_manifest.namespace_id == NS
    with pytest.raises(MediaContractError):
        MediaInspectionRequest(
            context=_ctx(),
            source_manifest=manifest,
            source_relative_ref="../secret.wav",
            expected_sha256=HASH,
        )
    with pytest.raises(MediaContractError):
        MediaInspectionRequest(
            context=_ctx(),
            source_manifest=manifest,
            source_relative_ref="tone.wav",
            expected_sha256="d" * 64,
        )


def test_accepted_inspection_requires_selection_and_toolchain() -> None:
    toolchain = fingerprint_toolchain(
        ffmpeg=_ffmpeg(), ffprobe=_ffprobe(), policy_version=SUBPROCESS_POLICY_VERSION
    )
    stream = InspectedStream(index=0, kind=StreamKind.AUDIO, codec_name="pcm_s16le", channels=1)
    result = MediaInspectionResult(
        state=MediaStepState.ACCEPTED,
        schema_version=INSPECTION_SCHEMA_VERSION,
        stream_count=1,
        streams=(stream,),
        toolchain=toolchain,
        container_format="wav",
        duration_us=100_000,
        selected_stream_index=0,
        selection_reason=StreamSelectionReason.LOWEST_SUPPORTED_INDEX,
    )
    assert result.selected_stream_index == 0
    with pytest.raises(MediaContractError) as exc:
        MediaInspectionResult(
            state=MediaStepState.ACCEPTED,
            schema_version=INSPECTION_SCHEMA_VERSION,
            stream_count=0,
            streams=(),
        )
    assert exc.value.code == "inspect.success"


def test_normalization_request_and_canonical_result_rules() -> None:
    manifest = synthetic_manifest()
    request = NormalizationRequest(
        context=_ctx(),
        source_manifest=manifest,
        source_relative_ref="tone.wav",
        selected_stream_index=0,
        selection_reason=StreamSelectionReason.EXPLICIT_INDEX,
        input_schema_version=NORMALIZATION_INPUT_SCHEMA_VERSION,
    )
    assert request.selected_stream_index == 0
    toolchain = fingerprint_toolchain(
        ffmpeg=_ffmpeg(), ffprobe=_ffprobe(), policy_version=SUBPROCESS_POLICY_VERSION
    )
    accepted = NormalizationResult(
        state=MediaStepState.ACCEPTED,
        schema_version=NORMALIZATION_SCHEMA_VERSION,
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
        duration_us=100_000,
        output_sha256="e" * 64,
        output_byte_size=3200,
        logical_uri="artifact://synth.example/canonical/tone",
        toolchain=toolchain,
    )
    assert accepted.output_sha256 is not None
    with pytest.raises(MediaContractError):
        NormalizationResult(
            state=MediaStepState.ACCEPTED,
            schema_version=NORMALIZATION_SCHEMA_VERSION,
            sample_rate_hz=8_000,
            channels=2,
            sample_width_bytes=2,
            output_sha256="e" * 64,
            output_byte_size=3200,
            logical_uri="artifact://synth.example/canonical/tone",
            toolchain=toolchain,
        )
    with pytest.raises(MediaContractError):
        NormalizationResult(
            state=MediaStepState.ACCEPTED,
            schema_version=NORMALIZATION_SCHEMA_VERSION,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            output_sha256="e" * 64,
            output_byte_size=3200,
            logical_uri="/tmp/out.wav",
            toolchain=toolchain,
        )


def test_tool_error_redacts_paths_and_stdio_keys() -> None:
    from speaker_attribution_video.media.enums import ToolFailureReason

    err = ToolError(
        ToolFailureReason.UNSAFE_CONFIGURATION,
        "executable configuration is unsafe",
        details={
            "path": "/Users/secret/bin/ffmpeg",
            "argv": ["ffmpeg", "-i", "/Users/secret/a.wav"],
            "note": "ok",
            "uri": "artifact://synth.example/media/tone",
        },
    )
    assert "/Users/" not in str(err)
    assert err.details["path"] == "<redacted>"
    assert err.details["argv"] == "<redacted>"
    assert err.details["note"] == "ok"
    assert err.details["uri"] == "artifact://synth.example/media/tone"


def test_version_and_identity_reject_malformed_inputs() -> None:
    with pytest.raises(MediaContractError):
        parse_tool_version_line("ffmpeg", "")
    with pytest.raises(MediaContractError):
        parse_tool_version_line("ffmpeg", "not a version line")
    with pytest.raises(MediaContractError):
        parse_tool_version_line("ffmpeg", "ffprobe version 8.0.1")
    with pytest.raises(MediaContractError):
        MediaToolIdentity(
            logical_name=ToolLogicalName.FFMPEG,
            version="8.0.1",
            version_sha256=_VERSION_SHA,
            schema_version="nope",
        )
    with pytest.raises(MediaContractError):
        MediaToolIdentity.from_dict(
            {
                "logical_name": "ffmpeg",
                "version": "8.0.1",
                "version_sha256": _VERSION_SHA,
                "capabilities": "nope",
            }
        )


def test_toolchain_requires_matching_tool_names() -> None:
    with pytest.raises(MediaContractError):
        fingerprint_toolchain(
            ffmpeg=_ffprobe(), ffprobe=_ffprobe(), policy_version=SUBPROCESS_POLICY_VERSION
        )


def test_policy_roundtrip_and_unsupported_version() -> None:
    policy = SubprocessPolicy()
    restored = SubprocessPolicy.from_dict(policy.to_dict())
    assert restored == policy
    with pytest.raises(MediaContractError):
        SubprocessPolicy(policy_version="mp1.nope.v1")


def test_inspection_result_rejects_path_warnings() -> None:
    with pytest.raises(MediaContractError):
        MediaInspectionResult(
            state=MediaStepState.REJECTED,
            schema_version=INSPECTION_SCHEMA_VERSION,
            stream_count=0,
            streams=(),
            warnings=("/Users/secret/file.wav",),
        )


def test_inspected_stream_rejects_invalid_codec_and_layout() -> None:
    with pytest.raises(MediaContractError):
        InspectedStream(index=0, kind=StreamKind.AUDIO, codec_name="pcm/s16")
    with pytest.raises(MediaContractError):
        InspectedStream(index=0, kind=StreamKind.AUDIO, channel_layout="left/right")
    stream = InspectedStream(
        index=1,
        kind=StreamKind.AUDIO,
        codec_name="aac",
        sample_rate_hz=44100,
        channels=2,
        duration_us=1000,
    )
    assert stream.identity_dict()["codec_name"] == "aac"


def test_normalization_rejects_job_mismatch() -> None:
    from speaker_attribution_video.graph.ids import JobId, NamespaceId

    other = NamespaceId.from_slug("other.example")
    ctx = RequestContext(namespace_id=other, job_id=JobId.derive(other, "job99"))
    with pytest.raises(MediaContractError):
        NormalizationRequest(
            context=ctx,
            source_manifest=synthetic_manifest(),
            source_relative_ref="tone.wav",
            selected_stream_index=0,
            selection_reason=StreamSelectionReason.EXPLICIT_INDEX,
        )
