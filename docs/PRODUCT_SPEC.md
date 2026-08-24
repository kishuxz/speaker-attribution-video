# Product specification

## Statement

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

## Goals

- Make attribution **inspectable**: every name assignment cites evidence nodes.
- Keep **diarization** (who spoke when, as SPEAKER_N) separate from **attribution** (mapping those clusters to names).
- Prefer an **unresolved** label over a guessed name.
- Bound agent retries and validation so loops cannot run unbounded.
- Support optional video evidence without requiring it.

## Non-goals (F0 and honest later)

- Not a deployed production service in this repository yet.
- Not a claim that prior private research was production-ready.
- Not redistribution of television corpora, transcripts, or weights.
- Not silent model download.
- InsightFace and LightASD are out of scope until license review.

## Users

Researchers and engineers who need an auditable speaker-attribution pipeline for licensed media they already have the right to process.

## Repository status

`kishuxz/speaker-attribution-video` is **private** during F0. Making it public is a separate decision.
