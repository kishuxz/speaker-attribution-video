# Security

## Reporting

Report vulnerabilities through GitHub **private vulnerability reporting** on
`kishuxz/speaker-attribution-video`. Do not open a public issue for security
reports.

Do not attach credentials, private research data, transcripts, or model weights
to reports.

## Scope (F0)

This repository is a foundation: documentation, an empty typed package, and a
CLI stub. There is no deployed service and no model-download path.

## Policy

- Never commit secrets. Use `.env.example` names only.
- Do not silently download third-party weights.
- Supply-chain changes (new dependencies) must be pinned in the lock file and reviewed.
