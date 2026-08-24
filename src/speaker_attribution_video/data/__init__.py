"""D1 source, rights, sensitivity, and media-manifest contracts.

These contracts describe artifacts. They do not process audio or video,
download datasets, or grant legal rights. User attestation is not independent
verification. The later policy engine is not legal advice.
"""

from __future__ import annotations

from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    DataSensitivity,
    MediaTypeStatus,
    RedactionState,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import ArtifactId, IngestionEventId, ManifestId, SourceId
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
    assert_manifest_schema_drift_free,
    canonical_bytes,
    canonical_dumps_manifest,
    loads_manifest,
)
from speaker_attribution_video.data.source import SourceDescriptor, make_source
from speaker_attribution_video.data.versions import (
    MANIFEST_SCHEMA_VERSION,
    RIGHTS_SCHEMA_VERSION,
    SOURCE_SCHEMA_VERSION,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RIGHTS_SCHEMA_VERSION",
    "SOURCE_SCHEMA_VERSION",
    "AcquisitionMethod",
    "ArtifactId",
    "DataContractError",
    "DataSensitivity",
    "IngestionEventId",
    "ManifestId",
    "MediaManifest",
    "MediaTypeStatus",
    "RedactionState",
    "RightsRecord",
    "RightsVerification",
    "SourceDescriptor",
    "SourceId",
    "SourceType",
    "StreamMetadata",
    "assert_manifest_schema_drift_free",
    "can_transition",
    "canonical_bytes",
    "canonical_dumps_manifest",
    "loads_manifest",
    "make_media_manifest",
    "make_source",
    "project_fixture_rights",
    "require_transition",
    "to_graph_sensitivity",
]
