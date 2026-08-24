# Evaluation

## Principles

- Publish only metrics produced by a **checked-in** evaluation command and a declared collar / overlap / scoring policy.
- Preserve **unresolved** rates; do not hide them inside accuracy.
- Do not cite unsupported historical notebook numbers from prior private research.

## F0

No evaluation harness yet. Smoke tests cover import and CLI only.

## Later

Evaluation should consume caller-supplied references (for example RTTM or similarly licensed annotations), never data from the private research tree. Reports belong under `outputs/` locally, not in git.
