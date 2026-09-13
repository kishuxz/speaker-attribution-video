# Publication review

This note records the checks run before changing `kishuxz/speaker-attribution-video`
from private to public.

## Candidate rationale

The repository is a strong public candidate because it is an original,
personally owned project with a focused purpose: tracing audio, transcript, and
optional video evidence into speaker-attribution decisions without overstating
model readiness. It demonstrates typed contracts, deterministic verification,
security/public-tree checks, limitations, Apache-2.0 licensing for original
source, and a staged issue/PR history.

## Safety checks

Run before publication:

- `gitleaks git --no-banner --redact --exit-code 99 .`
- GitHub secret-scanning alerts API query
- Current-tree sensitive-pattern scan for credentials and connection strings
- Git history path scan for env, credential, private-data, transcript, dataset,
  model, audio, and video indicators
- Git history large-blob scan for blobs over 256 KB
- Git LFS and submodule inspection
- Collaborator/contributor review

Findings:

- `gitleaks`: no leaks found.
- GitHub secret-scanning alerts API: unavailable because secret scanning is
  disabled for the private repository.
- Current-tree sensitive-pattern scan: only test literals and variable names;
  no credential values found.
- History path scan: expected source/docs/test paths only; no committed media,
  transcripts, datasets, model weights, `.env` values, or private-key files.
- Large-blob scan: no blobs over 256 KB.
- Git LFS/submodules: none found.
- Collaborators/contributors: only `kishuxz` was listed.

## Verification

Local verification was run on macOS with Python 3.11.16 in an isolated virtual
environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/verify.py
```

Result: `verify: all gates passed`.

Notable gate output:

- Public-tree scan passed for 144 tracked files.
- Ruff format/lint passed.
- Mypy passed with no issues in 57 source files.
- Unit tests: 165 passed, 50 deselected.
- Property tests: 20 passed, 195 deselected.
- Conformance tests: 30 passed, 185 deselected.
- Coverage run: 215 passed; total coverage 91.53%, above the 90% gate.
- Graph coverage policy: graph line coverage 96.76%, above the 95% gate.
- Graph and D1 data schema drift checks passed.
- Build, package inspection, `twine check`, clean wheel install/import, and CLI
  smoke check passed.
- `pip-audit --requirement requirements-dev.lock`: no known vulnerabilities
  found.

## Remaining limitations

- No real diarization, transcription, model inference, media processing, network
  dataset connector, agent execution, or public demo is implemented on `main`.
- Synthetic fixtures are not benchmark data.
- Coverage and conformance prove execution of contracts, not model accuracy.
- Apache-2.0 applies only to original source in this repository.
- Publication does not license or redistribute third-party datasets, media,
  transcripts, model weights, or research assets.
