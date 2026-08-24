# Product specification

## Statement

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

## Current phase (D1)

G1 contains typed evidence-graph contracts. T1 contains model-free verification. D1 adds source, rights, sensitivity, and media-manifest contracts. There is no real diarization, transcription, or model inference. “Agent” execution has not been implemented. Graph provenance is a record of claims and links; it is **not proof** that an attribution is correct. Confidence is not correctness.

Current fixtures are synthetic engineering tests, not accuracy benchmarks.

## Goals

- Make attribution **inspectable**: every name assignment cites evidence nodes.
- Keep **diarization** (who spoke when, as SPEAKER_N) separate from **attribution** (mapping those clusters to names).
- Prefer an **unresolved** label over a guessed name.
- Bound agent retries and validation so loops cannot run unbounded.
- Support optional video evidence without requiring it.

## Non-goals

- Not a deployed production service.
- Not a claim that prior private research was production-ready.
- Not redistribution of television corpora, transcripts, or weights.
- Not silent model download.
- InsightFace and LightASD are out of scope until license review.
- Media processing / model integration / agents are out of scope until D1 is reviewed.

## Users

Researchers and engineers who need an auditable speaker-attribution pipeline for licensed media they already have the right to process.

## Repository status

`kishuxz/speaker-attribution-video` is **private** during D1. Making it public is a separate decision.
