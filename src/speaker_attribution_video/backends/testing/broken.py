"""Broken backends used only to prove conformance suites detect defects.

These are not production doubles. They do not use environment-variable backdoors.
"""

from __future__ import annotations

from datetime import UTC, datetime

from speaker_attribution_video.backends.capabilities import Capabilities
from speaker_attribution_video.backends.contracts import (
    BACKEND_OUTPUT_SCHEMA_VERSION,
    AudioRequest,
    BackendIdentity,
    BackendResult,
    CancellationToken,
    DiarizationRequest,
    GraphFragment,
    HealthResult,
    RequestContext,
    TranscriptionRequest,
    VideoEvidenceRequest,
    fingerprint_config,
)
from speaker_attribution_video.backends.failures import ResultState
from speaker_attribution_video.backends.testing.fakes import (
    FAKE_VERSION,
    FakeAudioBackend,
    FakeDiarizationBackend,
    FakeTranscriptionBackend,
)
from speaker_attribution_video.graph.edges import EdgeType, GraphEdge
from speaker_attribution_video.graph.enums import ProducerKind, Sensitivity
from speaker_attribution_video.graph.ids import EdgeId, JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.nodes import (
    AudioArtifact,
    GraphNode,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=UTC)


class ConstantAudioBackend(FakeAudioBackend):
    """Ignores the request URI and always returns the same node."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        del request, cancel
        self.calls += 1
        ns = NamespaceId.from_slug("synth.example")
        job = JobId.derive(ns, "job01")
        node = make_node(
            namespace=ns,
            job=job,
            payload=AudioArtifact(
                content_hash="a" * 64,
                uri="artifact://synth.example/media/constant",
                display_name="synthetic-audio-01",
                duration_us=1_000_000,
            ),
            producer=Producer(ProducerKind.TEST, "broken.constant"),
            created_at=FIXED,
            identity_parts={"constant": "1", "job": job.value},
        )
        return BackendResult(
            state=ResultState.SUCCESS,
            identity=self.identity(),
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            fragment=GraphFragment(nodes=(node,), edges=()),
        )


class NamespaceRewritingAudioBackend(FakeAudioBackend):
    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        result = super().process(request, cancel=cancel)
        other_ns = NamespaceId.from_slug("other.example")
        other_job = JobId.derive(other_ns, "job99")
        assert result.fragment is not None
        rewritten: list[GraphNode] = []
        for node in result.fragment.nodes:
            payload = node.payload
            if isinstance(payload, AudioArtifact):
                rewritten.append(
                    make_node(
                        namespace=other_ns,
                        job=other_job,
                        payload=payload,
                        producer=node.producer,
                        created_at=FIXED,
                        identity_parts={"rewritten": "1", "job": other_job.value},
                    )
                )
        return BackendResult(
            state=ResultState.SUCCESS,
            identity=result.identity,
            output_schema_version=result.output_schema_version,
            fragment=GraphFragment(nodes=tuple(rewritten), edges=()),
        )


class TimeoutSuccessAudioBackend(FakeAudioBackend):
    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        if request.context.timeout_ms is not None and request.context.timeout_ms <= 0:
            honest_ctx = RequestContext(
                namespace_id=request.context.namespace_id,
                job_id=request.context.job_id,
                input_schema_version=request.context.input_schema_version,
                requested_capabilities=request.context.requested_capabilities,
                timeout_ms=None,
                metadata=request.context.metadata,
            )
            result = super().process(
                AudioRequest(context=honest_ctx, media=request.media), cancel=cancel
            )
            return BackendResult(
                state=ResultState.SUCCESS,
                identity=result.identity,
                output_schema_version=result.output_schema_version,
                fragment=result.fragment,
            )
        return super().process(request, cancel=cancel)


class MutatingAudioBackend(FakeAudioBackend):
    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        metadata = request.context.metadata
        if isinstance(metadata, dict):
            metadata["mutated"] = True
        return super().process(request, cancel=cancel)


class LeakTranscriptBackend(FakeTranscriptionBackend):
    def process(
        self, request: TranscriptionRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        try:
            return super().process(request, cancel=cancel)
        except Exception:
            raise RuntimeError("transcript=private-dialogue") from None


class OverlapClaimDiarizationBackend(FakeDiarizationBackend):
    def __init__(self) -> None:
        super().__init__(
            offered=Capabilities(offline=True, deterministic_replay=True, overlapping_speech=True)
        )

    def process(
        self, request: DiarizationRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        forced = DiarizationRequest(
            context=request.context,
            media=request.media,
            speaker_count_hint=request.speaker_count_hint,
            allow_overlap=False,
        )
        return super().process(forced, cancel=cancel)


class MissingEndpointDiarizationBackend(FakeDiarizationBackend):
    def process(
        self, request: DiarizationRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        result = super().process(request, cancel=cancel)
        assert result.fragment is not None
        ghost = EdgeId.derive(
            request.context.namespace_id,
            request.context.job_id,
            "DIARIZED_AS",
            NodeId.derive(
                request.context.namespace_id,
                request.context.job_id,
                "DiarizationTurn",
                {"ghost": "src"},
            ),
            NodeId.derive(
                request.context.namespace_id,
                request.context.job_id,
                "AudioArtifact",
                {"ghost": "dst"},
            ),
        )
        bogus = GraphEdge(
            id=ghost,
            edge_type=EdgeType.DIARIZED_AS,
            schema_version="g1.edge.v1",
            namespace_id=request.context.namespace_id,
            job_id=request.context.job_id,
            created_at=FIXED,
            producer=Producer(ProducerKind.TEST, "broken.edge"),
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            source_id=NodeId.derive(
                request.context.namespace_id,
                request.context.job_id,
                "DiarizationTurn",
                {"ghost": "src"},
            ),
            target_id=NodeId.derive(
                request.context.namespace_id,
                request.context.job_id,
                "AudioArtifact",
                {"ghost": "dst"},
            ),
        )
        return BackendResult(
            state=ResultState.SUCCESS,
            identity=result.identity,
            output_schema_version=result.output_schema_version,
            fragment=GraphFragment(
                nodes=result.fragment.nodes,
                edges=(*result.fragment.edges, bogus),
            ),
        )


class UnresolvedAsSuccessVideoBackend:
    def identity(self) -> BackendIdentity:
        return BackendIdentity(
            name="broken-video",
            version=FAKE_VERSION,
            configuration_fingerprint=fingerprint_config({"name": "broken-video"}),
            deterministic=True,
            input_schema_version="t1.backend.input.v1",
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            supports_timeout=True,
            supports_cancellation=True,
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(video_evidence=True, offline=True, deterministic_replay=True)

    def health(self) -> HealthResult:
        return HealthResult(ready=True, live=True)

    def close(self) -> None:
        return None

    def process(
        self, request: VideoEvidenceRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        del cancel
        return BackendResult(
            state=ResultState.SUCCESS,
            identity=self.identity(),
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            fragment=GraphFragment(nodes=(), edges=()),
        )


class VariableAudioBackend(FakeAudioBackend):
    def __init__(self) -> None:
        super().__init__(offered=Capabilities(offline=True, deterministic_replay=True))
        self._n = 0

    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        self._n += 1
        result = super().process(request, cancel=cancel)
        if result.fragment is None or self._n == 1:
            return result
        node = result.fragment.nodes[0]
        assert isinstance(node.payload, AudioArtifact)
        tweaked = make_node(
            namespace=node.namespace_id,
            job=node.job_id,
            payload=AudioArtifact(
                content_hash=node.payload.content_hash,
                uri=node.payload.uri,
                display_name="synthetic-audio-variant",
                duration_us=node.payload.duration_us,
            ),
            producer=node.producer,
            created_at=FIXED,
            identity_parts={"n": str(self._n), "job": node.job_id.value},
        )
        return BackendResult(
            state=ResultState.SUCCESS,
            identity=result.identity,
            output_schema_version=result.output_schema_version,
            fragment=GraphFragment(nodes=(tweaked,), edges=()),
        )
