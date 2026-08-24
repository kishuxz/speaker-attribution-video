"""Attribution admission rules. Confidence is not correctness and cannot admit ATTRIBUTED alone."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from speaker_attribution_video.graph.edges import EdgeType, GraphEdge
from speaker_attribution_video.graph.enums import DecisionState, NodeType, ReasonCode
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import NodeId
from speaker_attribution_video.graph.nodes import AttributionDecision, GraphNode


@dataclass(frozen=True, slots=True)
class AdmissionIssue:
    code: str
    message: str
    node_id: NodeId
    repair_category: str = "attribution"


@dataclass(frozen=True, slots=True)
class AttributionView:
    decision: GraphNode
    payload: AttributionDecision
    approved_candidate_ids: frozenset[NodeId]
    support_count: int
    contradict_count: int
    candidate_for_count: int
    reviewed_by_count: int


def view_attribution(
    decision: GraphNode,
    *,
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
) -> AttributionView:
    if decision.node_type is not NodeType.ATTRIBUTION_DECISION:
        raise GraphContractError("attribution.node", "node is not an attribution decision")
    payload = decision.payload
    if not isinstance(payload, AttributionDecision):
        raise GraphContractError("attribution.node", "node is not an attribution decision")
    approved = frozenset(n.id for n in nodes if n.node_type is NodeType.CANDIDATE_IDENTITY)
    support = sum(
        1 for e in edges if e.edge_type is EdgeType.SUPPORTS and e.target_id == decision.id
    )
    contra = sum(
        1 for e in edges if e.edge_type is EdgeType.CONTRADICTS and e.target_id == decision.id
    )
    cand_for = sum(
        1 for e in edges if e.edge_type is EdgeType.CANDIDATE_FOR and e.target_id == decision.id
    )
    reviewed = sum(
        1 for e in edges if e.edge_type is EdgeType.REVIEWED_BY and e.source_id == decision.id
    )
    return AttributionView(
        decision=decision,
        payload=payload,
        approved_candidate_ids=approved,
        support_count=support,
        contradict_count=contra,
        candidate_for_count=cand_for,
        reviewed_by_count=reviewed,
    )


def admit_attribution(view: AttributionView) -> tuple[AdmissionIssue, ...]:
    """Return structured issues. Does not inspect transcript text."""
    issues: list[AdmissionIssue] = []
    payload = view.payload
    nid = view.decision.id

    def add(code: str, message: str) -> None:
        issues.append(AdmissionIssue(code=code, message=message, node_id=nid))

    if payload.state is DecisionState.ATTRIBUTED:
        if payload.selected_candidate_id is None:
            add(
                "attribution.selected_required",
                "ATTRIBUTED requires exactly one selected candidate",
            )
        if view.support_count < 1:
            add(
                "attribution.evidence_required",
                "ATTRIBUTED requires at least one supporting evidence edge",
            )
        if payload.confidence_bp is not None and view.support_count < 1:
            add(
                "attribution.confidence_not_admission",
                "confidence cannot admit ATTRIBUTED without evidence",
            )
        if (
            payload.selected_candidate_id is not None
            and payload.selected_candidate_id not in view.approved_candidate_ids
        ):
            add(
                "attribution.candidate_set",
                "selected candidate is not in the approved candidate set",
            )
    elif payload.state is DecisionState.UNRESOLVED:
        if payload.selected_candidate_id is not None:
            add(
                "attribution.unresolved_identity", "UNRESOLVED must not contain a selected identity"
            )
    elif payload.state is DecisionState.CONTRADICTED:
        if view.contradict_count < 1:
            add(
                "attribution.contradiction_required", "CONTRADICTED requires contradictory evidence"
            )
    elif payload.state is DecisionState.REQUIRES_REVIEW:
        if payload.review_reason_code is None:
            add("attribution.review_reason", "REQUIRES_REVIEW must identify the reason for review")
    elif payload.state is DecisionState.REJECTED:
        if payload.reason_code not in (
            ReasonCode.REJECTED_BY_POLICY,
            ReasonCode.OUT_OF_CANDIDATE_SET,
            ReasonCode.VALIDATION_FAILED,
        ):
            add("attribution.rejected_reason", "REJECTED requires a typed rejection reason")

    if (
        payload.selected_candidate_id is not None
        and payload.selected_candidate_id not in view.approved_candidate_ids
        and payload.state is not DecisionState.ATTRIBUTED
    ):
        add(
            "attribution.candidate_set",
            "selected candidate is not in the approved candidate set",
        )

    return tuple(issues)


def require_admitted(view: AttributionView) -> None:
    issues = admit_attribution(view)
    if issues:
        raise GraphContractError(issues[0].code, issues[0].message)
