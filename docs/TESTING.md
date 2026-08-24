# Testing (T1 + D1 + MP1)

T1 is a **model-free** verification foundation. D1 adds contract tests for ingestion. MP1A/B add unit tests for media-tool contracts and a safe subprocess runner using **stub executables**. Passing conformance does **not** prove model accuracy. Coverage is evidence of **execution**, not correctness. Synthetic fixtures are **not** benchmark data. Model and GPU tests have not run. Core CI does **not** require FFmpeg.

Python **3.11** is the only supported runtime. A local 3.14 interpreter is an
environment mismatch, not a product failure.

## Entry point

```bash
python3.11 scripts/verify.py
```

Core CI markers: `unit`, `property`, `conformance`. Markers `integration`,
`model`, `gpu`, and `slow` are reserved for later real tests; empty placeholders
are forbidden. Skips are never counted as passes. Real FFmpeg checks belong in a
future `media-integration` job, not in core CI.

## Coverage policy (T1H)

Branch coverage is enabled. Line-coverage floors:

* `src/speaker_attribution_video/graph/` (graph and validation core): **95%**
* entire `src/` package: **90%**

Difficult production code is not omitted to inflate these numbers.
`scripts/check_coverage_policy.py` fails CI if either floor is missed.

## Property tests (T1G)

Hypothesis strategies are bounded (`max_examples=40` in the `ci` profile).
Failing examples are printed (`print_blob=True`) so seeds can be replayed.
Strategies generate integer timelines, overlapping turns, job/namespace pairs,
candidate sets, evidence edges, attribution states, correction attempts,
ordering permutations, canonical JSON round trips, path-traversal variants,
rights/sensitivity combinations, and snapshot idempotency. They never load private
research data.

## CI (T1J)

Four focused jobs run on Ubuntu with Python 3.11:

* `quality` — compile, Ruff format/lint, mypy
* `tests` — unit, property, conformance, coverage floors, G1 schema drift, D1 media-manifest schema drift; reports test count, skip count, and coverage
* `package` — sdist/wheel, content inspection, twine, isolated install
* `security-public-tree` — public-tree scan and dependency audit

macOS is not part of CI and is not claimed. Skips are never counted as passes. Model integration is not claimed.

## Packaging (T1I)

`python3.11 scripts/verify.py --job package` builds sdist and wheel, checks that G1 and D1 JSON Schema files and `py.typed` are included, excludes tests and development files, runs `twine check`, and installs the wheel into an empty virtualenv that does not depend on the source checkout.


CI fails if unit, property, or conformance collection drops to zero, if
collection errors occur, or if unexpected skips appear in the core suite.
