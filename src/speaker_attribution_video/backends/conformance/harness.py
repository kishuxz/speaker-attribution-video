"""Shared helpers for reusable backend conformance suites."""

from __future__ import annotations

from collections.abc import Mapping

from speaker_attribution_video.backends.capabilities import Capability
from speaker_attribution_video.backends.conformance.findings import check
from speaker_attribution_video.backends.contracts import (
    BACKEND_INPUT_SCHEMA_VERSION,
    GraphFragment,
    MediaRef,
    RequestContext,
)
from speaker_attribution_video.backends.failures import ResultState, is_successful
from speaker_attribution_video.graph.ids import JobId, NamespaceId
from speaker_attribution_video.graph.nodes import GraphNode
from speaker_attribution_video.graph.time import TimeSpan

HASH = "a" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
MEDIA = MediaRef(
    uri="artifact://synth.example/media/primary",
    content_hash=HASH,
    duration_us=1_000_000,
    display_name="synthetic-audio-01",
)


def context(
    *,
    metadata: Mapping[str, object] | None = None,
    requested_capabilities: frozenset[Capability] = frozenset(),
    timeout_ms: int | None = None,
    input_schema_version: str = BACKEND_INPUT_SCHEMA_VERSION,
    namespace_id: NamespaceId = NS,
    job_id: JobId = JOB,
) -> RequestContext:
    return RequestContext(
        namespace_id=namespace_id,
        job_id=job_id,
        metadata={"note": "ok"} if metadata is None else metadata,
        requested_capabilities=requested_capabilities,
        timeout_ms=timeout_ms,
        input_schema_version=input_schema_version,
    )


def assert_not_success(state: ResultState, finding: str) -> None:
    check(finding, not is_successful(state), f"{state.value} must not be counted as success")


def assert_fragment_integrity(
    fragment: GraphFragment,
    *,
    namespace: NamespaceId,
    job: JobId,
) -> None:
    ids = {node.id.value for node in fragment.nodes}
    for node in fragment.nodes:
        check(
            "namespace_job_preservation",
            node.namespace_id == namespace and node.job_id == job,
            "node escaped the request namespace or job",
        )
        check(
            "producer_metadata",
            bool(node.producer.name) and bool(node.producer.kind.value),
            "node is missing producer identity",
        )
    for edge in fragment.edges:
        check(
            "referential_integrity",
            edge.source_id.value in ids and edge.target_id.value in ids,
            "edge endpoint is missing from the fragment",
        )
        check(
            "namespace_job_preservation",
            edge.namespace_id == namespace and edge.job_id == job,
            "edge escaped the request namespace or job",
        )


def spans_within(node: GraphNode, duration_us: int) -> None:
    payload = node.payload
    span = getattr(payload, "span", None)
    if not isinstance(span, TimeSpan):
        return
    check("graph_output_validity", span.start_us >= 0, "span start is negative")
    check(
        "graph_output_validity",
        span.end_us <= duration_us,
        "span exceeds known media duration",
    )


def redacted_record(metadata: Mapping[str, object]) -> None:
    text = str(metadata)
    check("sensitive_redaction", "private-dialogue" not in text, "transcript leaked into metadata")
    check("sensitive_redaction", "/home/" not in text, "private path leaked into metadata")
