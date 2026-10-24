# Topia → Equus Migration Platform

Enterprise migration platform and automation engine that converts **Topia Full Historical Past Assignment** exports (`.xlsx`) into standard **Equus EAFH (Employee and Assignment File Hub)** bulk import workbooks, accompanied by comprehensive **Migration Results & Mapping Reports**.

---

## How It Works

1. **Source Ingestion & Header Alignment:**
   - Ingests Topia exports (`.xlsx`) containing up to 206 historical assignment attributes.
   - Maps each source column using its **Row-2 Equus Technical Field** to the corresponding **Row-3 Equus Import Header**; rule overrides and dictionaries live in `app/services/equus/mapping_config.py`.

2. **Row-1 Conversion Rules & Normalization:**
   - **Dates:** Converted to standardized ISO/US format (`YYYY-MM-DD`).
   - **Country Codes:** Converted to ISO-3166-1 alpha-3 codes (e.g., `United States` → `USA`, `United Kingdom` → `GBR`).
   - **Dropdowns & Dictionaries:** Normalized against Equus reference values (marital status, gender, currency, assignment types).
   - **Null Equivalents:** `"Not Provided"`, `"N/A"`, and whitespace are converted to clean blanks.

3. **Parent-Child & Command Semantics:**
   - **`INSERT` Row:** Generated for each assignment. The first child records (Address 1, Contact 1, Dependent 1) nest directly onto this row.
   - **`UPDATE` Rows:** Appended for additional child entities (Address 2+, Contact 2+, Dependent 2+). Sets `Employee Action = "IGNORE"` (Col A) and `Assignment Command = "UPDATE"` (Col B), referencing the parent `Assignment Identifier`.

4. **Deliverables Generated:**
   - **Equus Import File:** `local_s3/dest_s3/equus/<name>_EQUUS_<timestamp>.xlsx`  
     Formatted according to the bundled Equus EAFH template with technical instruction and header rows preserved.
   - **Migration Results Report:** `local_s3/dest_s3/equus/reports/<name>_MAPPING_REPORT_<timestamp>.xlsx`  
     Four-tab reconciliation deliverable containing:
     1. *Executive Summary:* Record counts, attempted/executed writes, destination verification status, and mapping coverage percentage.
     2. *Column Mappings:* Full source-to-target field dictionary with transformation types.
     3. *Translations Applied:* Value translations and dictionary conversions applied per field.
     4. *Warnings & Issues:* Pre-flight validation warnings, duplicate checks, rejected unlinked dependents, and read-back discrepancies.

---

## Execution Modes

The platform supports two complementary execution interfaces sharing the same pure business logic engine:

### Mode A: Standalone CLI Runner (S3-Compatible Local Batch)
Designed for offline batch execution and CI/CD pipelines without requiring Docker, MongoDB, or browser interaction. Uses local folders standing in for S3 buckets:
- **Input:** `local_s3/source_s3/topia/incoming/*.xlsx`
- **Output:** `local_s3/dest_s3/equus/` and `local_s3/dest_s3/equus/reports/`

### Mode B: Enterprise Web Platform & Demo Mode
Interactive React SPA + FastAPI backend providing real-time data profiling, Four-Eyes mapping approvals, asynchronous worker execution, and an isolated mock Equus destination (`MockEquusDestination`) for live client walkthroughs.

---

## Repository Layout

```
.
├── app/
│   ├── api/                    # FastAPI endpoints (sources, mappings, approvals, jobs, audit)
│   ├── core/                   # Security, configuration, and fail-closed target validators
│   ├── services/
│   │   └── equus/              # Pure Topia -> Equus transformation engine
│   │       ├── __init__.py     # Pipeline coordinator: run_equus_migration_pipeline()
│   │       ├── destination.py  # Isolated Mock Equus Destination engine (INSERT/UPDATE/idempotency)
│   │       ├── generator.py    # openpyxl workbook creators (Equus import + Results Report)
│   │       ├── mapping_config.py# 206-to-146 column mapping rules & value dictionaries
│   │       ├── reconciliation.py# Defensive data quality firewall & error aggregator
│   │       └── transformer.py  # Field-level converters (dates, country codes, child rows)
│   └── workers/                # Asynchronous job worker daemon
├── frontend/                   # React 18 + TypeScript + Vite web application
├── local/                      # Standalone CLI tools
│   └── run_local.py            # Local migration runner (simulating S3 bucket workflow)
├── local_s3/                   # Simulated S3 directory tree (incoming exports, generated imports)
├── docs/                       # Architecture, validation reports, and client demo guides
│   ├── CLIENT_DEMO_SCRIPT.md   # 8-stage client walkthrough script
│   ├── DEMO_WRITE_MODE_VALIDATION.md # Safe demo write mode verification report
│   └── reference-repository-analysis.md # Comparison with topia2equus reference implementation
├── tests/                      # Automated test suite (73 pytest unit, regression & demo write tests)
└── topia_equus_test_workbooks/ # Synthetic test fixtures (clean, numeric IDs, blanks, dirty data)
```

---

## Quick Start & Running Locally

### Prerequisites
- Python 3.10+ (tested through Python 3.13)
- Node.js 18+ (for frontend web UI)

### 1. Set Up Python Environment
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt  # or: pip install -e ".[dev]"
```

### 2. Run Migration via Local CLI Runner
Process a single file or an entire directory of incoming Topia exports:
```bash
# Run a specific file:
python local/run_local.py topia_equus_test_workbooks/01_valid_basic.xlsx

# Or process all workbooks placed in the incoming directory:
python local/run_local.py
```
Outputs are immediately written to:
- `local_s3/dest_s3/equus/01_valid_basic_EQUUS_<timestamp>.xlsx`
- `local_s3/dest_s3/equus/reports/01_valid_basic_MAPPING_REPORT_<timestamp>.xlsx`

### 3. Run Automated Tests
```bash
# Run full backend test suite (73 tests):
pytest tests/ -v

# Run frontend test suite:
cd frontend && npm test -- --run
```

### 4. Run Enterprise Web Platform (Optional)
```bash
# Terminal 1: Start Backend API (FastAPI)
python -m uvicorn app.main:app --port 8000

# Terminal 2: Start Background Worker
python -m app.workers.worker

# Terminal 3: Start Frontend SPA (Vite)
cd frontend && npm run dev
```
Open `http://localhost:5173` to access the migration dashboard.

---

## Safe Demo Write Mode & Target Boundaries

To demonstrate live `INSERT` and `UPDATE` execution during client presentations without risking production systems, the application includes an **Isolated Mock Destination Engine**:

- **Default Setting:** `EQUUS_WRITES_DISABLED=true` (All direct production writes are strictly blocked).
- **Demo Write Configuration:**
  ```bash
  EQUUS_TARGET="mock"
  MIGRATION_DEMO_WRITES_ENABLED="true"
  ```
- **Fail-Closed Security Guarantee:** Attempting to enable demo writes against any target other than `"mock"` raises an immediate error (`PermissionError` / HTTP 403 `LIVE_WRITES_DISABLED` or HTTP 422 `INVALID_DEMO_TARGET`). Live Equus API calls are structurally impossible in demo mode.

---

## Client Mapping Decisions & Configuration

The platform addresses all 6 key open mapping questions identified in the client specifications:

1. **Source Color Coding:**  
   Header-based mapping reads Row-2 technical names directly, making ingestion fully independent of visual cell colors.
2. **Assignment Identifier Strategy:**  
   Configurable via `--strategy`:
   - `Option A` (`TOPIA_ID_WITH_FALLBACK`): Authoritative Topia Assignment ID, falling back to Employee Number.
   - `Option B` (`EMPLOYEE_NUMBER`): Client default using Employee Number base with `-A1`, `-A2` multi-assignment suffixes.
3. **Resource Fields (`RESOURCE_MAP`):**  
   Lookup dictionary configured in `mapping_config.py`; unmapped consultants log clear warnings in Tab 4 rather than halting execution.
4. **Address Parsing:**  
   Multi-line parser decomposes address blocks into street, city, postal code, and ISO-3 country.
5. **Dependent Data Linkage:**  
   Embedded dependents on assignment rows link automatically; orphan dependents lacking an employee key are safely quarantined in Tab 4 (`UNLINKED_DEPENDENT`) without guessing parentage.
6. **Confirmed Defaults:**  
   Effective dates default to assignment start date; International Assignment derives from country mismatch; PII Nationality excluded by default.
