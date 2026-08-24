# Evaluation

## Principles

- Publish only metrics produced by a **checked-in** evaluation command and a declared collar / overlap / scoring policy.
- Preserve **unresolved** rates; do not hide them inside accuracy.
- Do not cite unsupported historical notebook numbers from prior private research.

## G1

No evaluation harness. Tests cover graph contracts and synthetic fixtures only. They are not model-integration tests and not accuracy benchmarks.

## D1

No accuracy evaluation. Manifest and rights tests are contract checks, not license verification and not diarization/transcription benchmarks. Synthetic tones prove ingestion behavior only; they are not accuracy benchmarks.

## Later

Evaluation should consume caller-supplied references (for example RTTM or similarly licensed annotations), never data from the private research tree. Reports belong under `outputs/` locally, not in git.
