# Speaker Attribution Graph

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

This repository (`kishuxz/speaker-attribution-video`) holds original source under Apache-2.0. It is **private during T1**. It is not a release of a production pipeline, and it does not ship models, datasets, or research media.

## Current phase (T1A/T1B)

G1 typed evidence-graph **contracts** are in place. T1 is adding a model-free verification system (tooling, quality gates, later backend conformance). There is still **no** real diarization, transcription, model inference, or agent execution.

```bash
python3.11 -m pip install -r requirements.lock
python3.11 -m pip install --require-hashes -r requirements-dev.lock
python3.11 -m pip install -e .
python3.11 -m speaker_attribution_video --help
python3.11 scripts/verify.py
```

Python **3.11** is the only supported runtime (`requires-python = ">=3.11,<3.12"`). A local Mac running Python 3.14 is an environment mismatch, not a product failure.

Regenerate lockfiles only with the commands in `requirements/README.md`. Do not hand-edit compiled lock output.

## What this is not

- Not a claim that prior research code was production-ready
- Not a redistribution of television corpora, transcripts, or logs
- Not a bundle of pyannote, WhisperX, ECAPA, Llama, InsightFace, or LightASD weights
- InsightFace and LightASD remain **research-only / license review required**
- Conformance and coverage, when added, do not prove model accuracy or correctness

See `docs/LIMITATIONS.md`, `docs/GRAPH.md`, `docs/MODEL_POLICY.md`, and `THIRD_PARTY_NOTICES.md`.
