"""Project an accepted D1 ingestion into a G1 evidence graph.

Rejected or partial ingestion cannot be represented as complete success.
This builder does not create diarization, transcript, speaker, or attribution
nodes, and it never embeds raw media bytes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from speaker_attribution_video.data.enums import IngestionState
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.manifest import MediaManifest
from speaker_attribution_video.data.sensitivity import to_graph_sensitivity
from speaker_attribution_video.data.serialize import (
    canonical_dumps_manifest,
    canonical_dumps_snapshot,
)
from speaker_attribution_video.data.snapshot import IngestionSnapshot
from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import NodeType, ProducerKind
from speaker_attribution_video.graph.ids import MediaId
from speaker_attribution_video.graph.nodes import (
    AudioArtifact,
    MediaArtifact,
    OutputArtifact,
    ProcessingStep,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.serialize import canonical_dumps_document
from speaker_attribution_video.graph.validate import validate_graph
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

_PRODUCER = Producer(ProducerKind.DETERMINISTIC, "ingestion.graph")
_SUCCESS = IngestionState.ACCEPTED


def _mime(manifest: MediaManifest) -> str:
    if manifest.media_type_detected is not None:
        return manifest.media_type_detected
    if manifest.media_type_declared is not None:
        return manifest.media_type_declared
    return "application/octet-stream"


def _container(mime: str) -> str | None:
    subtype = mime.split("/", 1)[-1]
    cleaned = subtype.replace("+", "-")
    if cleaned.replace("-", "").replace(".", "").isalnum() and cleaned[0].isalpha():
        return cleaned
    return None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def graph_from_accepted_ingestion(
    *,
    manifest: MediaManifest,
    snapshot: IngestionSnapshot,
    created_at: datetime,
) -> EvidenceGraphDocument:
    """Build a validated G1 graph from a fully accepted ingestion.

    ``created_at`` is an explicit observation timestamp so repeated projection
    of the same snapshot is byte-identical when the caller controls it.
    """

    if snapshot.state is not _SUCCESS or not snapshot.finalized:
        raise DataContractError(
            "graph.ingestion",
            "rejected or partial ingestion cannot be projected as success",
        )
    if manifest.namespace_id != snapshot.namespace_id or manifest.job_id != snapshot.job_id:
        raise DataContractError("graph.isolation", "manifest and snapshot jobs must match")
    accepted = tuple(entry for entry in snapshot.entries if entry.state is _SUCCESS)
    if len(accepted) != len(snapshot.entries) or not accepted:
        raise DataContractError(
            "graph.ingestion",
            "rejected or partial ingestion cannot be projected as success",
        )
    if all(entry.artifact_id != manifest.artifact_id for entry in accepted):
        raise DataContractError("graph.ingestion", "manifest artifact is not in the snapshot")

    sensitivity = to_graph_sensitivity(manifest.sensitivity)
    ns = manifest.namespace_id
    job = manifest.job_id
    mime = _mime(manifest)
    uri = manifest.source.logical_ref
    media_id = MediaId.derive(ns, job, manifest.content_sha256, uri)
    media = make_node(
        namespace=ns,
        job=job,
        payload=MediaArtifact(
            content_hash=manifest.content_sha256,
            mime_type=mime,
            uri=uri,
            display_name=manifest.logical_filename,
            media_id=media_id,
            duration_us=manifest.duration_us,
            container=_container(mime),
            byte_size=manifest.byte_size,
        ),
        producer=_PRODUCER,
        created_at=created_at,
        identity_parts={
            "content_hash": manifest.content_sha256,
            "job": job.value,
            "uri": uri,
        },
        metadata={
            "rights_verification": manifest.rights.verification.value,
            "source_type": manifest.source.source_type.value,
        },
        sensitivity=sensitivity,
    )
    step = make_node(
        namespace=ns,
        job=job,
        payload=ProcessingStep(
            step_name="ingest",
            sequence_index=0,
            parameters={
                "connector_name": manifest.connector_name,
                "connector_version": manifest.connector_version,
                "fingerprint": manifest.configuration_fingerprint,
            },
        ),
        producer=_PRODUCER,
        created_at=created_at,
        identity_parts={"job": job.value, "step": "ingest"},
        sensitivity=sensitivity,
        provenance_refs=(media.id.value,),
    )
    nodes = [media, step]
    edges = [
        make_edge(
            edge_type=EdgeType.PRODUCED_BY,
            source=media,
            target=step,
            producer=_PRODUCER,
            created_at=created_at,
            sensitivity=sensitivity,
        )
    ]
    if mime.startswith("audio/"):
        stream = manifest.audio_stream
        audio = make_node(
            namespace=ns,
            job=job,
            payload=AudioArtifact(
                content_hash=manifest.content_sha256,
                uri=uri,
                display_name=manifest.logical_filename,
                duration_us=manifest.duration_us,
                sample_rate_hz=stream.sample_rate_hz if stream is not None else None,
                channels=stream.channels if stream is not None else None,
                mime_type=mime,
                parent_media_id=media_id,
            ),
            producer=_PRODUCER,
            created_at=created_at,
            identity_parts={
                "content_hash": manifest.content_sha256,
                "job": job.value,
                "kind": "audio",
                "uri": uri,
            },
            sensitivity=sensitivity,
            provenance_refs=(media.id.value,),
        )
        nodes.append(audio)
        edges.append(
            make_edge(
                edge_type=EdgeType.EXTRACTED_FROM,
                source=audio,
                target=media,
                producer=_PRODUCER,
                created_at=created_at,
                sensitivity=sensitivity,
            )
        )
        edges.append(
            make_edge(
                edge_type=EdgeType.PRODUCED_BY,
                source=audio,
                target=step,
                producer=_PRODUCER,
                created_at=created_at,
                sensitivity=sensitivity,
            )
        )

    snapshot_hash = _sha256_text(canonical_dumps_snapshot(snapshot))
    manifest_hash = _sha256_text(canonical_dumps_manifest(manifest))
    snapshot_uri = f"artifact://ingestion.example/snapshots/{snapshot.snapshot_id.digest}"
    manifest_uri = f"artifact://ingestion.example/manifests/{manifest.manifest_id.digest}"
    snapshot_out = make_node(
        namespace=ns,
        job=job,
        payload=OutputArtifact(
            artifact_kind="ingestion-snapshot",
            uri=snapshot_uri,
            display_name="ingestion-snapshot",
            content_hash=snapshot_hash,
            media_type="application/json",
        ),
        producer=_PRODUCER,
        created_at=created_at,
        identity_parts={"digest": snapshot.snapshot_id.digest, "kind": "snapshot"},
        sensitivity=sensitivity,
        provenance_refs=(media.id.value, step.id.value),
    )
    manifest_out = make_node(
        namespace=ns,
        job=job,
        payload=OutputArtifact(
            artifact_kind="media-manifest",
            uri=manifest_uri,
            display_name="media-manifest",
            content_hash=manifest_hash,
            media_type="application/json",
        ),
        producer=_PRODUCER,
        created_at=created_at,
        identity_parts={"digest": manifest.manifest_id.digest, "kind": "manifest"},
        sensitivity=sensitivity,
        provenance_refs=(media.id.value, step.id.value),
    )
    nodes.extend((snapshot_out, manifest_out))
    edges.extend(
        (
            make_edge(
                edge_type=EdgeType.EMITTED_AS,
                source=step,
                target=snapshot_out,
                producer=_PRODUCER,
                created_at=created_at,
                sensitivity=sensitivity,
            ),
            make_edge(
                edge_type=EdgeType.EMITTED_AS,
                source=step,
                target=manifest_out,
                producer=_PRODUCER,
                created_at=created_at,
                sensitivity=sensitivity,
            ),
        )
    )
    document = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=ns,
        job_id=job,
        created_at=created_at,
        producer=_PRODUCER,
        metadata={
            "ingestion_state": snapshot.state.value,
            "snapshot_digest": snapshot.snapshot_id.digest,
        },
        sensitivity=sensitivity,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
    findings = validate_graph(document)
    errors = [item for item in findings if item.severity.value == "error"]
    if errors:
        raise DataContractError("graph.invalid", "ingestion graph failed G1 validation")
    forbidden = {NodeType.DIARIZATION_TURN, NodeType.TRANSCRIPT_UTTERANCE, NodeType.SPEAKER_CLUSTER}
    if any(node.node_type in forbidden for node in document.nodes):
        raise DataContractError("graph.ingestion", "D1 graphs must not include speaker nodes")
    encoded = canonical_dumps_document(document)
    if "RIFF" in encoded:
        raise DataContractError("graph.media", "raw media must not be embedded")
    return document


__all__ = ["graph_from_accepted_ingestion"]
