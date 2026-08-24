"""D1 source, rights, dataset, snapshot, and connector contracts.

These contracts describe artifacts. They do not process audio or video,
download datasets, or grant legal rights. User attestation is not independent
verification. The later policy engine is not legal advice.
"""

from __future__ import annotations

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
)
from speaker_attribution_video.data.dataset import (
    DatasetEntry,
    DatasetManifest,
    make_dataset_manifest,
)
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    DatasetSplit,
    IngestionFindingSeverity,
    IngestionState,
    IntendedUse,
    MediaTypeStatus,
    RedactionState,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import (
    ArtifactId,
    DatasetId,
    IngestionEventId,
    ManifestId,
    SnapshotId,
    SourceId,
)
from speaker_attribution_video.data.manifest import (
    MediaManifest,
    StreamMetadata,
    make_media_manifest,
)
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.sensitivity import (
    can_transition,
    require_transition,
    to_graph_sensitivity,
)
from speaker_attribution_video.data.serialize import (
    assert_data_schema_drift_free,
    assert_manifest_schema_drift_free,
    canonical_bytes,
    canonical_dumps_manifest,
    loads_manifest,
)
from speaker_attribution_video.data.snapshot import (
    IngestionFinding,
    IngestionSnapshot,
    SnapshotEntry,
    make_ingestion_snapshot,
)
from speaker_attribution_video.data.source import SourceDescriptor, make_source
from speaker_attribution_video.data.versions import (
    DATASET_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RIGHTS_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    SOURCE_SCHEMA_VERSION,
)

__all__ = [
    "DATASET_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RIGHTS_SCHEMA_VERSION",
    "SNAPSHOT_SCHEMA_VERSION",
    "SOURCE_SCHEMA_VERSION",
    "AcquisitionMethod",
    "ArtifactId",
    "ConnectorCapabilities",
    "ConnectorCapability",
    "ConnectorError",
    "ConnectorFailureReason",
    "ConnectorIdentity",
    "ConnectorRef",
    "ConnectorResult",
    "DataConnector",
    "DataContractError",
    "DataSensitivity",
    "DatasetEntry",
    "DatasetId",
    "DatasetManifest",
    "DatasetSplit",
    "IngestRequest",
    "IngestionEventId",
    "IngestionFinding",
    "IngestionFindingSeverity",
    "IngestionSnapshot",
    "IngestionState",
    "InspectRequest",
    "IntendedUse",
    "ManifestId",
    "MediaManifest",
    "MediaTypeStatus",
    "RedactionState",
    "RightsRecord",
    "RightsVerification",
    "SnapshotEntry",
    "SnapshotId",
    "SourceDescriptor",
    "SourceId",
    "SourceType",
    "StreamMetadata",
    "ValidateRequest",
    "assert_data_schema_drift_free",
    "assert_manifest_schema_drift_free",
    "can_transition",
    "canonical_bytes",
    "canonical_dumps_manifest",
    "loads_manifest",
    "make_dataset_manifest",
    "make_ingestion_snapshot",
    "make_media_manifest",
    "make_source",
    "project_fixture_rights",
    "require_connector_capabilities",
    "require_transition",
    "to_graph_sensitivity",
]
