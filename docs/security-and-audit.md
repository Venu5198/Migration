# Security and audit

Workbooks are accepted only as OOXML `.xlsx` by default; `.xlsm` needs explicit configuration and remains data-only (macros are never executed). Filenames are flattened/sanitized, payloads are size-limited, magic bytes are checked, and a SHA-256 digest plus private storage reference is recorded. Uploads, workbooks, CSVs, reports, and `.env` are ignored by Git.

No secrets or live destination credentials are included. Production deployment must configure authenticated access, viewer/approver/executor authorization, CORS origins, encrypted private storage, retention/deletion policy, audit event collection, secret manager integration, and export formula-injection escaping before handling client data.

The application implements bearer-token RBAC with constant-time token comparison (`hmac.compare_digest`). Development can explicitly disable authentication for local testing; production startup strictly fails closed if `MIGRATION_AUTH_TOKENS` or `MIGRATION_MONGODB_URI` is missing or unreachable. Ephemeral in-memory persistence is strictly forbidden in production.

CSV exports are hardened against formula injection: any value whose stripped representation starts with `=`, `+`, `-`, `@`, `\t`, `\r`, `|`, or `%` is escaped with a leading apostrophe.

Separation of duties is enforced: mapping authors cannot approve their own mappings when authentication is active, and approved mappings cannot be re-approved or mutated without version incrementing.

Audit events are persisted as metadata-only records in `audit_events` for uploads, source access, mapping creation, updates, approvals, job creation, claiming, cancellation, completion, failures, CSV export downloads, and reconciliation queries. No raw cell values or secrets are stored in audit logs. Access to audit event history is restricted to the `admin` role.
