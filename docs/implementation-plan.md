# Implementation plan

## Current assessment (2026-10-22)

The supplied project root was empty and not a Git repository. It was initialized locally with no client workbooks, existing source, tests, Docker configuration, CI, credentials, or remote history to preserve. The initial implementation therefore uses synthetic test workbooks only.

## Delivered Phase 1–3 slice

- Configuration, private storage directories, structured errors, health endpoint, MongoDB lifecycle boundary.
- Safe `.xlsx` upload policy, size limit, filename sanitization, magic-byte check, SHA-256, multi-sheet inventory, duplicate/missing-header findings.
- Worker-separated profiling job with atomic Mongo lease design; memory fallback is explicitly non-durable.
- Mapping creation/approval safety rule and deterministic approved-direct-mapping dry-run previews.

## Next increments

1. Complete mapping version history, reviewers, deterministic suggestions, and validation constraints.
2. Add transformation/preview records and CSV/XLSX exports with formula-injection protection.
3. Add issue persistence, pagination, cancellation, audit events, retention policy, and role authorization.
4. Add sanitized 50,000-row benchmark, CI, and target connector contract once client approval exists.

