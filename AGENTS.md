# Agent instructions

This repository is the **public-project foundation** for Speaker Attribution Graph (`kishuxz/speaker-attribution-video`). It may be public only when the publication-safety review passes.

## Rules

1. **Python 3.11 only.** Do not add 3.12+ or 3.10 syntax or classifiers. A local Python 3.14 interpreter is an environment mismatch, not a product failure.
2. **Do not copy implementation** from the private research repository `kishuxz/speaker-diarization` (or any clone of it). Provenance belongs in `docs/RESEARCH_PROVENANCE.md` at documentation level only.
3. **Do not download models or datasets.** Do not use Hugging Face credentials. Do not vendor weights.
4. **InsightFace and LightASD** are research-only until independent license review. Do not implement or import them here.
5. **Do not publish** research datasets, transcripts, dialogue fixtures, show names in examples, weights, W&B metadata, SLURM logs, private paths, personal metadata, or unsupported historical metrics.
6. **Apache-2.0** applies only to original public source in this repo. Do not claim it covers third-party models or datasets.
7. **PR discipline:** one issue per change; one focused PR; no direct pushes to `main`; tests and docs required; merge only with green CI; do not create artificial commit activity.
8. **Stop at the current approved phase.** T1 and D1 (safe data contracts and local ingestion) are complete on `main`. Do not start media processing, real backends, agents, model integration, or a public demo unless that later phase is explicitly scoped and reviewed. D1 connectors must not decode audio/video, invoke ffmpeg, or copy media into the package.
9. Preserve honest limitations. Unresolved cases stay unresolved; do not invent speaker names in examples.

## Package layout

Original code lives under `src/speaker_attribution_video/`. Data contracts live under `src/speaker_attribution_video/data/`. Third-party vendor stubs remain in `integrations/protocols.py`. Model-neutral backend contracts live under `src/speaker_attribution_video/backends/`. Deterministic fakes are test utilities in `backends/testing/`.

## Verification

```bash
python3.11 -m pip install -r requirements.lock
python3.11 -m pip install --require-hashes -r requirements-dev.lock
python3.11 -m pip install -e .
python3.11 scripts/verify.py
```
