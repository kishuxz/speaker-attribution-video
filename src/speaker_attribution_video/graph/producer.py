"""Producer identity for graph records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from speaker_attribution_video.graph.enums import ProducerKind, parse_enum
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import require_slug


@dataclass(frozen=True, slots=True)
class Producer:
    kind: ProducerKind
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProducerKind):
            raise GraphContractError("producer.kind", "producer kind is invalid")
        require_slug(self.name, label="producer.name")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "name": self.name}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Producer:
        kind = parse_enum(ProducerKind, data.get("kind"), code="producer.kind")
        name = data.get("name")
        if not isinstance(name, str):
            raise GraphContractError("producer.name", "producer name is invalid")
        return cls(kind=kind, name=name)  # type: ignore[arg-type]
