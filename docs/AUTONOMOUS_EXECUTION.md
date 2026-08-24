# Autonomous execution

Instructions for coding agents and humans working this repository.

## Current approved phase

**F0 only.** Do not begin G1, do not copy production logic from private research, do not download models.

## Loop

1. Read `AGENTS.md`, `docs/LIMITATIONS.md`, and the issue.
2. Implement on a branch.
3. Run `python3.11 -m pytest` and `python3.11 scripts/check_public_tree.py`.
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
