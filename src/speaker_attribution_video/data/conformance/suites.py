"""Reusable DataConnector conformance suite. Not an accuracy benchmark."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime

from speaker_attribution_video.backends.conformance.findings import ConformanceFailure, check
from speaker_attribution_video.backends.contracts import CancellationToken, RequestContext
from speaker_attribution_video.data.connector import (
    ConnectorError,
    ConnectorRef,
    DataConnector,
    IngestRequest,
    InspectRequest,
)
from speaker_attribution_video.data.enums import (
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    IngestionState,
    RightsVerification,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.graph import graph_from_accepted_ingestion
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.versions import CONNECTOR_INPUT_SCHEMA_VERSION
from speaker_attribution_video.graph.enums import NodeType
from speaker_attribution_video.graph.ids import JobId, NamespaceId
from speaker_attribution_video.graph.time import utc_now_for_tests

NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
Factory = Callable[[], DataConnector]


def _ctx(*, metadata: dict[str, object] | None = None) -> RequestContext:
    return RequestContext(
        namespace_id=NS,
        job_id=JOB,
        input_schema_version=CONNECTOR_INPUT_SCHEMA_VERSION,
        metadata=metadata if metadata is not None else {},
    )


def _unoffered(connector: DataConnector) -> ConnectorCapability:
    offered = connector.capabilities().offered()
    for cap in ConnectorCapability:
        if cap not in offered:
            return cap
    raise ConformanceFailure("capability_honesty", "connector claims every capability")


def conform_data_connector(
    factory: Factory,
    target: ConnectorRef,
    *,
    rights: RightsRecord | None = None,
    sensitivity: DataSensitivity = DataSensitivity.SYNTHETIC,
    expected_digest: str | None = None,
    created_at: datetime | None = None,
    forbidden_target: ConnectorRef | None = None,
) -> None:
    """Assert protocol honesty for a DataConnector factory.

    Passing this suite does not prove model accuracy or license validity.
    """

    connector = factory()
    check("protocol_compliance", bool(connector.identity().name), "identity name missing")
    check("protocol_compliance", bool(connector.identity().version), "identity version missing")
    caps = connector.capabilities()
    check(
        "protocol_compliance",
        caps.checksum_verification and caps.immutable_snapshots,
        "required capabilities were not offered",
    )
    unoffered = _unoffered(connector)
    try:
        factory().inspect(
            InspectRequest(
                context=_ctx(),
                target=target,
                requested_capabilities=frozenset({unoffered}),
                rights=rights,
                sensitivity=sensitivity,
            )
        )
        raise ConformanceFailure("capability_honesty", "unsupported capability was accepted")
    except ConnectorError as exc:
        check(
            "capability_honesty",
            exc.reason is ConnectorFailureReason.UNSUPPORTED_CAPABILITY,
            "wrong reason for unsupported capability",
        )

    inspect_req = InspectRequest(
        context=_ctx(),
        target=target,
        rights=rights,
        sensitivity=sensitivity,
    )
    first = factory().inspect(inspect_req)
    second = factory().inspect(inspect_req)
    check("typed_failures", bool(first.manifests), "inspect returned no manifests")
    check(
        "deterministic_behavior",
        first.manifests[0].content_sha256 == second.manifests[0].content_sha256,
        "repeated inspect was not deterministic",
    )
    check(
        "deterministic_behavior",
        first.manifests[0].manifest_id == second.manifests[0].manifest_id,
        "manifest identity was not stable",
    )
    check(
        "namespace_job_preservation",
        first.manifests[0].namespace_id == NS and first.manifests[0].job_id == JOB,
        "namespace or job was rewritten",
    )
    if expected_digest is not None:
        check(
            "checksum_correctness",
            first.manifests[0].content_sha256 == expected_digest,
            "content digest does not match source bytes",
        )
    check(
        "immutable_snapshot_output",
        first.snapshot is not None and first.snapshot.finalized,
        "inspect did not return a finalized snapshot",
    )
    snapshot = first.snapshot
    if snapshot is None:
        raise ConformanceFailure("immutable_snapshot_output", "inspect returned no snapshot")
    if first.state is IngestionState.ACCEPTED:
        check(
            "complete_success",
            snapshot.state is IngestionState.ACCEPTED,
            "accepted result wrapped a non-accepted snapshot",
        )
        check(
            "failed_entries_visible",
            all(entry.state is IngestionState.ACCEPTED for entry in snapshot.entries),
            "accepted snapshot omitted a failed entry by dropping it",
        )
    if caps.synthetic_generation:
        check(
            "sensitivity_preservation",
            first.manifests[0].sensitivity is DataSensitivity.SYNTHETIC,
            "synthetic fixture sensitivity was not preserved",
        )
    else:
        check(
            "sensitivity_preservation",
            first.manifests[0].sensitivity is sensitivity,
            "sensitivity was rewritten",
        )
        check(
            "sensitivity_preservation",
            first.manifests[0].sensitivity is not DataSensitivity.PUBLIC
            or sensitivity is DataSensitivity.PUBLIC,
            "sensitivity was silently downgraded to public",
        )
    if (
        not caps.synthetic_generation
        and rights is not None
        and rights.verification is RightsVerification.UNVERIFIED
    ):
        check(
            "unknown_rights_redistributable",
            first.manifests[0].rights.redistribution_permitted is not True,
            "unknown rights were marked redistributable",
        )
    if rights is not None:
        check(
            "rights_enforcement",
            first.manifests[0].rights.verification is rights.verification
            or caps.synthetic_generation,
            "caller rights were ignored without a synthetic fixture policy",
        )

    try:
        factory().inspect(
            InspectRequest(
                context=RequestContext(
                    namespace_id=NS,
                    job_id=JOB,
                    input_schema_version="not-a-schema",
                ),
                target=target,
                rights=rights,
                sensitivity=sensitivity,
            )
        )
        raise ConformanceFailure("schema_version", "unsupported schema was accepted")
    except ConnectorError as exc:
        check(
            "schema_version",
            exc.reason is ConnectorFailureReason.SCHEMA_MISMATCH,
            "wrong reason for schema mismatch",
        )

    token = CancellationToken()
    token.cancel()
    try:
        factory().inspect(inspect_req, cancel=token)
        raise ConformanceFailure("cancellation", "cancelled inspect succeeded")
    except ConnectorError as exc:
        check(
            "cancellation",
            exc.reason is ConnectorFailureReason.CANCELLATION,
            "wrong reason for cancellation",
        )

    metadata: dict[str, object] = {"note": "ok"}
    original = deepcopy(metadata)
    factory().inspect(
        InspectRequest(
            context=_ctx(metadata=metadata),
            target=target,
            rights=rights,
            sensitivity=sensitivity,
        )
    )
    check("no_input_mutation", metadata == original, "caller metadata was mutated")

    closed = factory()
    closed.close()
    check("cleanup", True, "close() must be callable")

    if first.state is IngestionState.ACCEPTED:
        observed = created_at if created_at is not None else utc_now_for_tests()
        graph = graph_from_accepted_ingestion(
            manifest=first.manifests[0],
            snapshot=snapshot,
            created_at=observed,
        )
        types = {node.node_type for node in graph.nodes}
        check("graph_validity", NodeType.MEDIA_ARTIFACT in types, "media node missing")
        check(
            "graph_validity",
            NodeType.DIARIZATION_TURN not in types,
            "D1 graph included diarization nodes",
        )
        check(
            "namespace_job_preservation",
            graph.namespace_id == NS and graph.job_id == JOB,
            "graph rewrote namespace or job",
        )
    else:
        try:
            graph_from_accepted_ingestion(
                manifest=first.manifests[0],
                snapshot=snapshot,
                created_at=created_at or utc_now_for_tests(),
            )
            raise ConformanceFailure(
                "graph_validity",
                "rejected ingestion produced a success graph",
            )
        except DataContractError as exc:
            check("graph_validity", exc.code == "graph.ingestion", "wrong rejection code")

    try:
        factory().inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="../secret", display_name="x"),
                rights=rights,
                sensitivity=sensitivity,
            )
        )
        if not caps.synthetic_generation:
            raise ConformanceFailure("path_escape", "path traversal was accepted")
    except ConnectorError as exc:
        check(
            "no_sensitive_error_leakage",
            "/Users/" not in str(exc) and "/home/" not in str(exc),
            "absolute path leaked in an error",
        )
        if not caps.synthetic_generation:
            check(
                "path_escape",
                exc.reason is ConnectorFailureReason.PATH_ESCAPE,
                "path traversal used the wrong failure reason",
            )

    if forbidden_target is not None:
        try:
            factory().inspect(
                InspectRequest(
                    context=_ctx(),
                    target=forbidden_target,
                    rights=rights,
                    sensitivity=sensitivity,
                )
            )
            raise ConformanceFailure("path_escape", "escaped path was ingested")
        except ConnectorError as exc:
            check(
                "path_escape",
                exc.reason is ConnectorFailureReason.PATH_ESCAPE,
                "escaped path used the wrong failure reason",
            )
            check(
                "no_sensitive_error_leakage",
                "/Users/" not in str(exc) and "/home/" not in str(exc),
                "absolute path leaked in an error",
            )

    ingest = factory().ingest(
        IngestRequest(
            context=_ctx(),
            targets=(target,),
            rights=rights,
            sensitivity=sensitivity,
        )
    )
    check("protocol_compliance", ingest.snapshot is not None, "ingest returned no snapshot")
    check(
        "immutable_snapshot_output",
        ingest.snapshot is not None and ingest.snapshot.finalized,
        "ingest snapshot was not finalized",
    )
