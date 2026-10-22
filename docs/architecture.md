# Architecture

The prototype is a FastAPI service, a separate Python worker, an OOXML workbook service, and a repository boundary. Business services do not call FastAPI or Equus. Uploads are private filesystem references; MongoDB stores metadata, mappings, jobs, and audit-ready summaries rather than workbook binaries.

`POST upload -> secure private file -> schema inventory -> source metadata -> 202 job -> atomic worker claim -> profile/preview result`.

When `MIGRATION_MONGODB_URI` is configured, `MongoRepository` creates `sources`, `mappings`, and `migration_jobs` indexes. Job claims use MongoDB `find_one_and_update`, a lease expiry, and attempt counter, avoiding unsafe read-then-update queue behavior. Without MongoDB, an ephemeral repository supports local API exploration only.

Equus is represented by a safety boundary: no connector is registered and health explicitly reports writes as disabled. A confirmed REST, bulk-import, or other official contract is required before execution work.
