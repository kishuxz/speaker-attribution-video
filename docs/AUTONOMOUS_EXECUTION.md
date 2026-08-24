# Autonomous execution

Instructions for coding agents and humans working this repository.

## Current approved phase

**T1 in progress.** T1G/T1H add Hypothesis graph properties and honest coverage floors. T1 still has no real audio or model processing. Do not begin D1 until the T1 report is reviewed.

## Loop

1. Read `AGENTS.md`, `docs/LIMITATIONS.md`, and the issue.
2. Implement on a branch from current `main`.
3. Run `python3.11 scripts/verify.py`.
4. Open a focused PR; merge only with green CI.

## Hard stops

- No direct commits to `main` after the bootstrap empty commit.
- No history rewrite.
- No Hugging Face credential use.
- No GPU/HPC jobs from this repository in F0.
- No package publish, deploy, or GitHub Release.
- No InsightFace / LightASD implementation.

## Honesty

If a speaker cannot be attributed, the system (when implemented) must leave the case unresolved. Agents must not fabricate evaluation numbers or show-specific shortcuts.
