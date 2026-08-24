# Backend contracts (T1C/T1D)

T1 defines **model-neutral protocols** and **deterministic test doubles**. There is no real audio processing, diarization, transcription, video identity, or model inference. Passing a fake-backend test does not prove model accuracy.

Vendor stubs in `src/speaker_attribution_video/integrations/protocols.py` remain documentation-only (pyannote, Whisper, InsightFace, LightASD). They are not implementations of these contracts.

## Protocols

| Protocol | Package |
|---|---|
| `AudioBackend` | `speaker_attribution_video.backends` |
| `DiarizationBackend` | `speaker_attribution_video.backends` |
| `TranscriptionBackend` | `speaker_attribution_video.backends` |
| `AlignmentBackend` | `speaker_attribution_video.backends` |
| `VideoEvidenceBackend` | `speaker_attribution_video.backends` |
| `AttributionModelBackend` | `speaker_attribution_video.backends` |
| `TelemetryBackend` | `speaker_attribution_video.backends` |

Each protocol exposes identity, version, configuration fingerprint, capability descriptor, input/output schema versions, timeout and cancellation support, health/readiness, typed failures, and `close()`.

## Honesty rules

- Unsupported capabilities raise `BackendError` with `FailureReason.UNSUPPORTED_CAPABILITY`. They must not degrade silently.
- `ResultState.DEGRADED` and `UNRESOLVED` are never `SUCCESS`.
- Exceptions and telemetry must not include transcript text, raw media, tokens, or private filesystem paths.
- Fake backends live in `speaker_attribution_video.backends.testing` and accept `artifact://synth.example/` inputs only.
- Reusable conformance suites live in `speaker_attribution_video.backends.conformance`. Future backends must call those helpers rather than copying tests. Anti-vacuity backends in `backends.testing.broken` exist only to prove the suites fail with stable finding codes.
- D1 data contracts live in `speaker_attribution_video.data`. `DataConnector` is a source-neutral protocol for inspect/ingest of declared local or synthetic references. There is no HTTP, S3, Hugging Face, or database connector.

## Result and failure taxonomies

Result states: `SUCCESS`, `DEGRADED`, `UNRESOLVED`, `FAILED_VALIDATION`, `FAILED_BACKEND`, `FAILED_TIMEOUT`, `FAILED_CANCELLED`, `FAILED_RESOURCE_LIMIT`.

Failure reasons: `invalid_input`, `unsupported_capability`, `unavailable_backend`, `missing_model`, `timeout`, `cancellation`, `resource_limit`, `malformed_output`, `schema_mismatch`, `external_dependency_failure`, `unsafe_configuration`, `privacy_policy_rejection`.
