# Contributing

## Process

1. Open an issue for the change.
2. Work on a branch. Do not push commits to `main`.
3. Include tests and documentation for the change.
4. Open a focused pull request that closes the issue.
5. Merge only when CI is green.

## Environment

- Python **3.11** only
- `python3.11 -m pip install -e ".[dev]"`
- `python3.11 -m pytest`
- `python3.11 scripts/check_public_tree.py`

Do not commit `.env`, media, weights, transcripts, training JSONL, W&B metadata, or SLURM logs.

Synthetic fixtures belong only under `tests/fixtures/synthetic/` and must not use real show names or dialogue from private research.

## License

Contributions are original source under Apache-2.0 (`LICENSE`). Do not contribute third-party weights or material you cannot license.
