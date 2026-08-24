"""G1 property smoke tests. T1G expands this suite; this file is not a placeholder."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.time import TimeSpan

pytestmark = pytest.mark.property

_US = st.integers(min_value=0, max_value=10_000_000)


@given(start=_US, duration=st.integers(min_value=1, max_value=1_000_000))
def test_valid_integer_spans_round_trip(start: int, duration: int) -> None:
    span = TimeSpan(start, start + duration)
    restored = TimeSpan.from_dict(span.to_dict())
    assert restored == span
    assert restored.duration_us() == duration


@given(start=_US, end=_US)
def test_invalid_span_order_is_rejected(start: int, end: int) -> None:
    if end > start:
        return
    with pytest.raises(GraphContractError) as exc:
        TimeSpan(start, end)
    assert exc.value.code in {"span.order", "span.end"}
    assert "transcript" not in str(exc.value).lower()
