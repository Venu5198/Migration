# API specification

Implemented endpoints:

- `GET /health` — service/database state; Equus writes always disabled.
- `GET /live`, `GET /ready` — process liveness and dependency readiness.
- `POST /api/v1/sources/upload` — private `.xlsx` upload and worksheet inventory.
- `GET /api/v1/sources`, `GET /api/v1/sources/{source_id}`, `GET /api/v1/sources/{source_id}/sheets`.
- `POST /api/v1/sources/{source_id}/profile` — creates a `202` profiling job.
- `POST /api/v1/mappings`, `GET /api/v1/mappings/{mapping_id}`, `PUT /api/v1/mappings/{mapping_id}`, `POST /api/v1/mappings/{mapping_id}/approve`.
- `POST /api/v1/migrations/preview` — queues a dry-run for approved direct mappings. It reads only the source workbook and never writes to Equus.
- `GET /api/v1/jobs/{job_id}`.
- `POST /api/v1/jobs/{job_id}/cancel`, `GET /api/v1/reports/{job_id}/export`, `GET /api/v1/targets/mock/test-connection`.
- `GET /api/v1/mappings/{mapping_id}/versions`, `GET /api/v1/audit-events` (admin only), and `GET /api/v1/reports/{job_id}/reconciliation`.

Errors are structured as `{ "error": { "code", "message" } }` for domain validation errors. Jobs expose `PENDING`, `RUNNING`, terminal status, attempts, result, and failure code.

Security and Validation Controls:
- Mappings validate that `source_sheet` and `source_field` exist in the source workbook schema. Unresolved mapping types (`unresolved`) can propose ambiguous fields pending client decision, but cannot be approved until resolved.
- Mapping approvals are immutable and enforce separation of duties (author cannot approve their own mapping when auth is active).
- Approved mappings cannot be mutated via `PUT /api/v1/mappings/{mapping_id}`.
- Exports and reconciliation queries generate auditable lineage records.

