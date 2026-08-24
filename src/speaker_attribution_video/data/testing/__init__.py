"""Broken D1 doubles. Not production connectors."""

from speaker_attribution_video.data.testing.broken import (
    ConstantHashConnector,
    IgnoreInputConnector,
    MutatingConnector,
    NamespaceRewritingConnector,
    OverwritingSnapshotStore,
    PartialAsSuccessConnector,
    PathLeakingConnector,
    SensitivityDowngradeConnector,
    SymlinkEscapeConnector,
    UnknownRightsRedistributableConnector,
    unsafe_graph_from_rejected,
)

__all__ = [
    "ConstantHashConnector",
    "IgnoreInputConnector",
    "MutatingConnector",
    "NamespaceRewritingConnector",
    "OverwritingSnapshotStore",
    "PartialAsSuccessConnector",
    "PathLeakingConnector",
    "SensitivityDowngradeConnector",
    "SymlinkEscapeConnector",
    "UnknownRightsRedistributableConnector",
    "unsafe_graph_from_rejected",
]
