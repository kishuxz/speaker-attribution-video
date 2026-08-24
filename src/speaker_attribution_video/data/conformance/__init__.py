"""Reusable D1 connector conformance. Future connectors must call these helpers."""

from speaker_attribution_video.backends.conformance.findings import ConformanceFailure, check
from speaker_attribution_video.data.conformance.suites import conform_data_connector

__all__ = ["ConformanceFailure", "check", "conform_data_connector"]
