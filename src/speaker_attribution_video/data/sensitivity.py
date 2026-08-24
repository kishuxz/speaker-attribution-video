"""Sensitivity ranks and non-downgrade transitions."""

from __future__ import annotations

from speaker_attribution_video.data.enums import DataSensitivity
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.graph.enums import Sensitivity as GraphSensitivity

# Higher number is more sensitive. UNKNOWN cannot be treated as public.
_RANK: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.SYNTHETIC: 1,
    DataSensitivity.INTERNAL: 2,
    DataSensitivity.CONFIDENTIAL: 3,
    DataSensitivity.PERSONAL_DATA: 4,
    DataSensitivity.RESTRICTED: 5,
    DataSensitivity.BIOMETRIC_DATA: 6,
    DataSensitivity.UNKNOWN: 5,
}

_TO_GRAPH: dict[DataSensitivity, GraphSensitivity] = {
    DataSensitivity.PUBLIC: GraphSensitivity.PUBLIC,
    DataSensitivity.SYNTHETIC: GraphSensitivity.INTERNAL,
    DataSensitivity.INTERNAL: GraphSensitivity.INTERNAL,
    DataSensitivity.CONFIDENTIAL: GraphSensitivity.SENSITIVE,
    DataSensitivity.RESTRICTED: GraphSensitivity.RESTRICTED,
    DataSensitivity.PERSONAL_DATA: GraphSensitivity.SENSITIVE,
    DataSensitivity.BIOMETRIC_DATA: GraphSensitivity.RESTRICTED,
    DataSensitivity.UNKNOWN: GraphSensitivity.RESTRICTED,
}


def rank(value: DataSensitivity) -> int:
    return _RANK[value]


def can_transition(current: DataSensitivity, proposed: DataSensitivity) -> bool:
    """True when proposed is equal or more sensitive. Silent downgrade is forbidden."""
    if current is DataSensitivity.UNKNOWN and proposed is DataSensitivity.PUBLIC:
        return False
    return rank(proposed) >= rank(current)


def require_transition(current: DataSensitivity, proposed: DataSensitivity) -> None:
    if not can_transition(current, proposed):
        raise DataContractError(
            "sensitivity.downgrade",
            "sensitivity cannot be silently downgraded",
        )


def to_graph_sensitivity(value: DataSensitivity) -> GraphSensitivity:
    """Map D1 sensitivity onto G1 node sensitivity without downgrading restrictiveness."""
    return _TO_GRAPH[value]


def require_unambiguous(*, sensitivity: DataSensitivity, redistribution: bool) -> None:
    if sensitivity is DataSensitivity.UNKNOWN and redistribution:
        raise DataContractError(
            "sensitivity.ambiguous",
            "unknown sensitivity cannot be marked redistributable",
        )
    if (
        sensitivity in {DataSensitivity.PERSONAL_DATA, DataSensitivity.BIOMETRIC_DATA}
        and redistribution
    ):
        raise DataContractError(
            "sensitivity.redistribution",
            "personal or biometric data cannot be marked redistributable",
        )
    if sensitivity is DataSensitivity.RESTRICTED and redistribution:
        raise DataContractError(
            "sensitivity.redistribution",
            "restricted data cannot be marked redistributable",
        )
