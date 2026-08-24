"""Invariant validator. Findings never include raw transcript text."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from typing import Mapping

from speaker_attribution_video.graph.attribution import admit_attribution, view_attribution
from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import ACYCLIC_EDGE_TYPES, EdgeType, matrix_allows
from speaker_attribution_video.graph.enums import FindingSeverity, NodeType, RepairCategory
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import EdgeId, NodeId
from speaker_attribution_video.graph.nodes import (
    AudioArtifact,
    AudioSegment,
    CorrectionAttempt,
    DiarizationTurn,
    GraphNode,
    HumanReviewDecision,
    MediaArtifact,
    TranscriptToken,
    TranscriptUtterance,
)
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.versions import SUPPORTED_GRAPH_SCHEMA_VERSIONS


@dataclass(frozen=True, slots=True)
class GraphFinding:
    code: str
    severity: FindingSeverity
    message: str
    repair_category: RepairCategory
    node_id: NodeId | None = None
    edge_id: EdgeId | None = None


class GraphValidationError(GraphContractError):
    def __init__(self, findings: tuple[GraphFinding, ...]) -> None:
        self.findings = findings
        codes = ",".join(sorted({f.code for f in findings}))
        super().__init__("graph.invalid", f"graph rejected: {codes}")


def validate_graph(document: EvidenceGraphDocument) -> tuple[GraphFinding, ...]:
    findings: list[GraphFinding] = []

    def err(
        code: str,
        message: str,
        *,
        repair: RepairCategory,
        node_id: NodeId | None = None,
        edge_id: EdgeId | None = None,
    ) -> None:
        findings.append(
            GraphFinding(
                code=code,
                severity=FindingSeverity.ERROR,
                message=message,
                repair_category=repair,
                node_id=node_id,
                edge_id=edge_id,
            )
        )

    if document.schema_version not in SUPPORTED_GRAPH_SCHEMA_VERSIONS:
        err("graph.schema", "unsupported graph schema version", repair=RepairCategory.SCHEMA)

    node_ids: dict[str, GraphNode] = {}
    for node in document.nodes:
        if node.namespace_id != document.namespace_id or node.job_id != document.job_id:
            err(
                "graph.isolation",
                "node is outside the document namespace or job",
                repair=RepairCategory.ISOLATION,
                node_id=node.id,
            )
        if node.id.value in node_ids:
            err("graph.duplicate_node", "duplicate node id", repair=RepairCategory.IDENTIFIER, node_id=node.id)
        else:
            node_ids[node.id.value] = node

    edge_ids: dict[str, object] = {}
    triples: set[tuple[str, str, str]] = set()
    for edge in document.edges:
        if edge.namespace_id != document.namespace_id or edge.job_id != document.job_id:
            err(
                "graph.isolation",
                "edge is outside the document namespace or job",
                repair=RepairCategory.ISOLATION,
                edge_id=edge.id,
            )
        if edge.id.value in edge_ids:
            err("graph.duplicate_edge", "duplicate edge id", repair=RepairCategory.IDENTIFIER, edge_id=edge.id)
        else:
            edge_ids[edge.id.value] = edge
        triple = (edge.edge_type.value, edge.source_id.value, edge.target_id.value)
        if triple in triples:
            err("graph.duplicate_edge", "duplicate edge endpoints and type", repair=RepairCategory.IDENTIFIER, edge_id=edge.id)
        triples.add(triple)
        src = node_ids.get(edge.source_id.value)
        tgt = node_ids.get(edge.target_id.value)
        if src is None or tgt is None:
            err(
                "graph.endpoint",
                "edge endpoint is missing",
                repair=RepairCategory.EDGE_MATRIX,
                edge_id=edge.id,
            )
            continue
        if src.namespace_id != tgt.namespace_id:
            err("graph.isolation", "cross-namespace edge", repair=RepairCategory.ISOLATION, edge_id=edge.id)
        if src.job_id != tgt.job_id:
            err("graph.isolation", "cross-job edge", repair=RepairCategory.ISOLATION, edge_id=edge.id)
        if not matrix_allows(edge.edge_type, src.node_type, tgt.node_type):
            err("graph.matrix", "edge type is not allowed for these endpoints", repair=RepairCategory.EDGE_MATRIX, edge_id=edge.id)
        if edge.edge_type in (EdgeType.SUPPORTS, EdgeType.CONTRADICTS) and tgt.node_type is not NodeType.ATTRIBUTION_DECISION:
            err("graph.evidence_target", "evidence does not point at an attribution decision", repair=RepairCategory.ATTRIBUTION, edge_id=edge.id)

    _validate_outputs(document, node_ids, err)
    _validate_timeline(document, node_ids, err)
    _validate_attribution(document, err)
    _validate_corrections(document, node_ids, err)
    _validate_reviews(document, node_ids, err)
    _validate_acyclic(document, err)
    return tuple(findings)


def load_graph(data: Mapping[str, object]) -> EvidenceGraphDocument:
    document = EvidenceGraphDocument.from_dict_unvalidated(data)
    findings = validate_graph(document)
    errors = tuple(f for f in findings if f.severity is FindingSeverity.ERROR)
    if errors:
        raise GraphValidationError(errors)
    return document


def _validate_outputs(document: EvidenceGraphDocument, node_ids: dict[str, GraphNode], err) -> None:
    produced = {e.source_id.value for e in document.edges if e.edge_type is EdgeType.PRODUCED_BY}
    emitted = {e.target_id.value for e in document.edges if e.edge_type is EdgeType.EMITTED_AS}
    for node in document.nodes:
        if node.node_type is NodeType.OUTPUT_ARTIFACT and node.id.value not in produced and node.id.value not in emitted:
            err(
                "graph.output_producer",
                "output artifact has no producing step",
                repair=RepairCategory.PROVENANCE,
                node_id=node.id,
            )


def _validate_timeline(document: EvidenceGraphDocument, node_ids: dict[str, GraphNode], err) -> None:
    durations: dict[str, int] = {}
    for node in document.nodes:
        payload = node.payload
        if isinstance(payload, (MediaArtifact, AudioArtifact)) and payload.duration_us is not None:
            durations[node.id.value] = payload.duration_us

    for node in document.nodes:
        payload = node.payload
        if isinstance(payload, AudioSegment):
            src = node_ids.get(payload.source_node_id.value)
            if src is None:
                err("graph.timeline_ref", "segment source is missing", repair=RepairCategory.TIMELINE, node_id=node.id)
            else:
                duration = durations.get(src.id.value)
                try:
                    payload.span.within_duration(duration)
                except GraphContractError:
                    err("graph.timeline_bounds", "segment exceeds known media duration", repair=RepairCategory.TIMELINE, node_id=node.id)
        if isinstance(payload, TranscriptToken):
            utt = node_ids.get(payload.utterance_id.value)
            if utt is None or not isinstance(utt.payload, TranscriptUtterance):
                err("graph.token_utterance", "token utterance is missing", repair=RepairCategory.TIMELINE, node_id=node.id)
            elif not utt.payload.span.contains(payload.span):
                err("graph.token_bounds", "token span is outside its utterance", repair=RepairCategory.TIMELINE, node_id=node.id)
        if isinstance(payload, DiarizationTurn):
            _check_turn_media(document, node, payload.span, durations, node_ids, err)


def _check_turn_media(document, node, span: TimeSpan, durations, node_ids, err) -> None:
    for edge in document.edges:
        if edge.source_id != node.id or edge.edge_type is not EdgeType.DIARIZED_AS:
            continue
        target = node_ids.get(edge.target_id.value)
        if target is None:
            continue
        duration = durations.get(target.id.value)
        if isinstance(target.payload, AudioSegment):
            if not target.payload.span.contains(span):
                err("graph.turn_bounds", "turn is outside its audio segment", repair=RepairCategory.TIMELINE, node_id=node.id)
            duration = durations.get(target.payload.source_node_id.value, duration)
        try:
            span.within_duration(duration)
        except GraphContractError:
            err("graph.turn_bounds", "turn exceeds known media duration", repair=RepairCategory.TIMELINE, node_id=node.id)


def _validate_attribution(document: EvidenceGraphDocument, err) -> None:
    for node in document.nodes:
        if node.node_type is not NodeType.ATTRIBUTION_DECISION:
            continue
        view = view_attribution(node, nodes=document.nodes, edges=document.edges)
        for issue in admit_attribution(view):
            err(issue.code, issue.message, repair=RepairCategory.ATTRIBUTION, node_id=issue.node_id)


def _validate_corrections(document: EvidenceGraphDocument, node_ids: dict[str, GraphNode], err) -> None:
    by_target: dict[str, list[GraphNode]] = defaultdict(list)
    for node in document.nodes:
        if node.node_type is not NodeType.CORRECTION_ATTEMPT:
            continue
        payload = node.payload
        if not isinstance(payload, CorrectionAttempt):
            continue
        target = node_ids.get(payload.target_decision_id.value)
        if target is None or target.job_id != document.job_id:
            err("graph.correction_job", "correction cannot target another job", repair=RepairCategory.CORRECTION, node_id=node.id)
            continue
        if target.node_type is not NodeType.ATTRIBUTION_DECISION:
            err("graph.correction_target", "correction target is not a decision", repair=RepairCategory.CORRECTION, node_id=node.id)
            continue
        finding = node_ids.get(payload.finding_id.value)
        if finding is None or finding.node_type is not NodeType.VALIDATION_FINDING:
            err("graph.correction_finding", "correction finding is missing", repair=RepairCategory.CORRECTION, node_id=node.id)
        if payload.attempt_number > document.max_correction_attempts:
            err("graph.correction_bound", "correction attempt exceeds the configured maximum", repair=RepairCategory.CORRECTION, node_id=node.id)
        if payload.resulting_decision_id is not None:
            result = node_ids.get(payload.resulting_decision_id.value)
            if result is None:
                err("graph.correction_result", "resulting decision is missing", repair=RepairCategory.CORRECTION, node_id=node.id)
            elif result.id == target.id:
                err("graph.correction_overwrite", "correction must not overwrite the prior decision", repair=RepairCategory.CORRECTION, node_id=node.id)
        by_target[payload.target_decision_id.value].append(node)

    for _target, attempts in by_target.items():
        numbers = sorted(
            n.payload.attempt_number for n in attempts if isinstance(n.payload, CorrectionAttempt)
        )
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            err(
                "graph.correction_sequence",
                "correction attempt numbers must be sequential starting at 1",
                repair=RepairCategory.CORRECTION,
                node_id=attempts[0].id,
            )


def _validate_reviews(document: EvidenceGraphDocument, node_ids: dict[str, GraphNode], err) -> None:
    reviewed = {e.target_id.value: e.source_id for e in document.edges if e.edge_type is EdgeType.REVIEWED_BY}
    for node in document.nodes:
        if node.node_type is not NodeType.HUMAN_REVIEW_DECISION:
            continue
        payload = node.payload
        if not isinstance(payload, HumanReviewDecision):
            continue
        original = node_ids.get(payload.target_decision_id.value)
        if original is None:
            err("graph.review_target", "review target is missing", repair=RepairCategory.REVIEW, node_id=node.id)
            continue
        if payload.replacement_decision_id is not None:
            replacement = node_ids.get(payload.replacement_decision_id.value)
            if replacement is None:
                err("graph.review_replacement", "replacement decision is missing", repair=RepairCategory.REVIEW, node_id=node.id)
            elif replacement.id == original.id:
                err("graph.review_overwrite", "review override must retain the original decision", repair=RepairCategory.REVIEW, node_id=node.id)


def _validate_acyclic(document: EvidenceGraphDocument, err) -> None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    edge_for: dict[tuple[str, str], EdgeId] = {}
    for edge in document.edges:
        if edge.edge_type not in ACYCLIC_EDGE_TYPES:
            continue
        adjacency[edge.source_id.value].append(edge.target_id.value)
        edge_for[(edge.source_id.value, edge.target_id.value)] = edge.id
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for nxt in adjacency.get(node, ()):
            if dfs(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for node in list(adjacency):
        if dfs(node):
            err(
                "graph.cycle",
                "derivation/provenance cycle is not permitted",
                repair=RepairCategory.PROVENANCE,
            )
            return
