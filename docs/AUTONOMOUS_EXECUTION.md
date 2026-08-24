# Autonomous execution

Instructions for coding agents and humans working this repository.

## Current approved phase

**T1 complete pending review.** T1 is verification foundations only: tooling, contracts, fake backends, conformance, properties, coverage, packaging, and CI. Do not begin D1, media processing, real backends, agents, model integration, or a public demo until the T1 report is reviewed.

## Loop

1. Read `AGENTS.md`, `docs/LIMITATIONS.md`, `docs/TESTING.md`, and the issue.
2. Implement on a branch from current `main`.
3. Run `python3.11 scripts/verify.py`.
4. Open a focused PR; merge only with green CI.

## Hard stops

- No direct commits to `main` after the bootstrap empty commit.
- No history rewrite.
- No Hugging Face credential use.
- No GPU/HPC jobs from this repository in T1.
- No package publish, deploy, or GitHub Release.
- No InsightFace / LightASD implementation.
- Do not start D1 until the T1 stop report is reviewed.

## Honesty

If a speaker cannot be attributed, the system (when implemented) must leave the case unresolved. Agents must not fabricate evaluation numbers or show-specific shortcuts. Coverage is not correctness. Conformance of a fake backend is not model accuracy.
