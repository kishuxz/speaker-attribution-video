# Speaker Attribution Graph

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

This repository (`kishuxz/speaker-attribution-video`) holds original source under Apache-2.0. It is **private during MP1**. It is not a release of a production pipeline, and it does not ship models, datasets, or research media.

## Current phase (MP1)

T1 (model-free verification) and D1 (safe ingestion contracts) are complete. MP1 adds **toolchain contracts** and a **safe subprocess runner** for separately installed FFprobe/FFmpeg. Canonical normalization, the audio artifact store, and real-tool CI follow in later MP1 PRs. There is still **no** diarization, transcription, model inference, agent execution, or public demo. FFmpeg is **not** Apache-2.0-relicensed by this repository.

Passing a conformance suite does **not** prove model accuracy. Coverage is evidence of execution, not correctness. Synthetic fixtures are not benchmark data. Model and GPU tests have not run. Core CI remains FFmpeg-free.

```bash
python3.11 -m pip install -r requirements.lock
python3.11 -m pip install --require-hashes -r requirements-dev.lock
python3.11 -m pip install -e .
python3.11 -m speaker_attribution_video --help
python3.11 scripts/verify.py
```

Python **3.11** is the only supported runtime (`requires-python = ">=3.11,<3.12"`). A local Mac running Python 3.14 is an environment mismatch, not a product failure.

CI runs four focused jobs on **Ubuntu / Python 3.11**: `quality`, `tests`, `package`, and `security-public-tree`. macOS is not claimed.

Regenerate lockfiles only with the commands in `requirements/README.md`. Do not hand-edit compiled lock output.

See `docs/TESTING.md`, `docs/BACKEND_CONTRACTS.md`, `docs/INGESTION.md`, `docs/MEDIA_PROCESSING.md`, `docs/FFMPEG.md`, `docs/DATASET_MANIFEST.md`, `docs/LIMITATIONS.md`, `docs/GRAPH.md`, `docs/MODEL_POLICY.md`, and `THIRD_PARTY_NOTICES.md`.

## What this is not

- Not a claim that prior research code was production-ready
- Not a redistribution of television corpora, transcripts, or logs
- Not a bundle of pyannote, WhisperX, ECAPA, Llama, InsightFace, or LightASD weights
- InsightFace and LightASD remain **research-only / license review required**
- Conformance and coverage do not prove model accuracy or correctness
