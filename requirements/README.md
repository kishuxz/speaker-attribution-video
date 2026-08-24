# Dependency locks

Runtime and development dependencies are separate. There are **no** model, audio,
video, GPU, or graph-database packages.

Python **3.11** is the only supported interpreter. A local Mac running Python 3.14
is an environment mismatch, not a product failure.

Do not hand-edit compiled lock output. Regenerating a lock requires the
documented command below, run with CPython 3.11.

## Runtime (`requirements.lock`)

This package currently has **zero** runtime third-party dependencies.
`requirements/runtime.in` is intentionally empty of package pins.
`requirements.lock` is a comment-only file that records that fact.

If runtime dependencies are added later, compile them with:

```bash
python3.11 -m pip install 'pip==24.3.1' 'pip-tools==7.4.1'
CUSTOM_COMPILE_COMMAND="python3.11 -m piptools compile --generate-hashes -o requirements.lock requirements/runtime.in" \
  python3.11 -m piptools compile --generate-hashes -o requirements.lock requirements/runtime.in
```

`pip-tools==7.4.1` requires `pip<25` while compiling. Installing from the lock
does not require pinning pip.

## Development (`requirements-dev.lock`)

Direct development pins live in `requirements/dev.in`.

Regenerate:

```bash
python3.11 -m pip install 'pip==24.3.1' 'pip-tools==7.4.1'
CUSTOM_COMPILE_COMMAND="python3.11 -m piptools compile --generate-hashes --strip-extras -o requirements-dev.lock requirements/dev.in" \
  python3.11 -m piptools compile --generate-hashes --strip-extras -o requirements-dev.lock requirements/dev.in
```

Install into an empty Python 3.11 environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install -e .
```

Packaging remains setuptools + wheel. Do not switch backends without a
documented reason.
