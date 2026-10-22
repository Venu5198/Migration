# Testing strategy

Unit/API tests create only an in-memory synthetic workbook. They cover health safety, format rejection, dynamic worksheet discovery, schema findings, mapping approval gating, worker claim/profile completion. Tests never connect to Equus and do not require MongoDB.

Run `pytest` and `ruff check .`. Future integration tests must use an isolated MongoDB; benchmark tests must generate sanitized 50,000-row workbooks and report actual runtime/memory. Client workbooks are not test fixtures until sanitized and approved.

