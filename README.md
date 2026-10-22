# Migration

Local-first, review-driven Excel migration API. It securely inventories `.xlsx` workbooks, profiles worksheet schemas, records validation issues, manages versioned mappings, and produces dry-run previews. Equus writes are intentionally disabled pending a confirmed integration contract.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Run `pytest` and `ruff check .` before commits. MongoDB is optional for local exploration; without `MIGRATION_MONGODB_URI`, the API uses ephemeral in-memory metadata and reports a degraded database health state. Docker Compose provisions MongoDB for durable local use.

See [documentation](docs/architecture.md) for architecture, safety boundaries, APIs, testing, and unresolved client decisions.
