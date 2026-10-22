# Operations

Use `docker compose up --build` for API, worker, and MongoDB. MongoDB is internal to the Compose network and has no host port. `GET /live` verifies process liveness; `GET /ready` verifies required MongoDB readiness when configured. Stop with `docker compose down`; preserve local volumes for backup with `docker compose down` (without `-v`). Back up MongoDB using a controlled `mongodump` procedure and copy private upload storage consistently with the database metadata.

Production requires `MIGRATION_MONGODB_URI`, `MIGRATION_ENV=production`, and secret-managed `MIGRATION_AUTH_TOKENS`; startup fails if production tokens are absent. Tokens have the format `token:subject:viewer|approver|executor|admin` and must not be committed. File deletion is intentionally not automated until the client approves retention policy.

Run Mongo integration tests only with an isolated disposable database: `$env:MIGRATION_TEST_MONGODB_URI='mongodb://localhost:27017/migration_test'; python -m pytest tests/test_mongo_integration.py`. Do not point this variable at production. For a 50,000-row benchmark, use sanitized/generated workbooks only; no measured performance claim is made by this prototype.

Run the generated benchmark with `python scripts/benchmark_50000.py`; it creates the workbook in a temporary directory and removes it automatically. Report metadata is stored separately from reports and includes only report/job/digest/mapping references. No automated retention period is configured because the client retention decision is unresolved; cleanup must be introduced only with an approved policy and application-root path validation.
