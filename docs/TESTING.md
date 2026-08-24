# Testing (T1)

T1 is a **model-free** verification foundation. Tests use synthetic fixtures and
deterministic fake backends only. Passing conformance does **not** prove model
accuracy. Coverage is evidence of **execution**, not correctness. Synthetic
fixtures are **not** benchmark data. Model, GPU, and integration tests have
not run.

Python **3.11** is the only supported runtime. A local 3.14 interpreter is an
environment mismatch, not a product failure.

## Entry point

```bash
python3.11 scripts/verify.py
```

Core CI markers: `unit`, `property`, `conformance`. Markers `integration`,
`model`, `gpu`, and `slow` are reserved for later real tests; empty placeholders
are forbidden. Skips are never counted as passes.

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
ordering permutations, and canonical JSON round trips. They never load private
research data.

## CI (T1J)

Four focused jobs run on Ubuntu with Python 3.11:

* `quality` — compile, Ruff format/lint, mypy
* `tests` — unit, property, conformance, coverage floors, schema drift; reports test count, skip count, and coverage
* `package` — sdist/wheel, content inspection, twine, isolated install
* `security-public-tree` — public-tree scan and dependency audit

macOS is not part of CI and is not claimed. Skips are never counted as passes. Model integration is not claimed.

## Packaging (T1I)

`python3.11 scripts/verify.py --job package` builds sdist and wheel, checks that JSON Schema and `py.typed` are included, excludes tests and development files, runs `twine check`, and installs the wheel into an empty virtualenv that does not depend on the source checkout.


CI fails if unit, property, or conformance collection drops to zero, if
collection errors occur, or if unexpected skips appear in the core suite.
