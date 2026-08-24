# Contributing

## Process

1. Open an issue for the change.
2. Work on a branch. Do not push commits to `main`.
3. Include tests and documentation for the change.
4. Open a focused pull request that closes the issue.
5. Merge only when CI is green.

## Environment

- Python **3.11** only (`requires-python = ">=3.11,<3.12"`).
- Python 3.14 on a local Mac is an environment mismatch, not a product failure.
- Install from locks (empty 3.11 environment):

```bash
python3.11 -m pip install -r requirements.lock
python3.11 -m pip install --require-hashes -r requirements-dev.lock
python3.11 -m pip install -e .
python3.11 scripts/verify.py
```

`scripts/verify.py` is the cross-platform gate. It stops on the first failure, preserves the failing command and exit code, and never downloads models, requires credentials, starts Docker, or calls paid APIs.

Core CI markers are `unit`, `property`, and `conformance`. Do not add empty `integration` / `model` / `gpu` placeholders.

Lock regeneration commands are in `requirements/README.md`. Do not hand-edit compiled lockfiles.

See `docs/TESTING.md`. Coverage is evidence of execution, not correctness. Graph/validation core must stay at or above 95% line coverage; the whole `src/` package at or above 90%. Branch coverage is enabled.

Do not commit `.env`, media, weights, transcripts, training JSONL, W&B metadata, or SLURM logs.

Synthetic fixtures belong only under `tests/fixtures/synthetic/` and must not use real show names or dialogue from private research.

## License

Contributions are original source under Apache-2.0 (`LICENSE`). Do not contribute third-party weights or material you cannot license.
