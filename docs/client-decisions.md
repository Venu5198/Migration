# Client decisions required before production migration

The platform deliberately does not infer these requirements: authoritative workbooks/sheets; approved source-to-target mappings; required Equus fields; employee and assignment keys; country/status dictionaries; job-title versus job-level semantics; historical/concurrent/cancelled assignment scope; duplicate policy; Equus integration and authentication; insert/update/rollback policy; identity provider and role assignments; retention/deletion/access policy.

Until these decisions are recorded, previews may use approved deterministic direct/trim/upper/lower mappings only. Equus writes remain disabled.
