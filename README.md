# Topia → Equus Migration Platform

Enterprise migration platform and automation engine that converts **Topia Full Historical Past Assignment** exports (`.xlsx`) into standard **Equus EAFH (Employee and Assignment File Hub)** bulk import workbooks, accompanied by comprehensive **Migration Results & Mapping Reports**.

---

## Architecture Overview

```
                      ┌──────────────────────────────────────────┐
                      │    Topia Historical Export (.xlsx)       │
                      │  Row 1: Rules | Row 2-3: Instructions   │
                      │  Row 4: Canonical Headers | Row 5+: Data│
                      └────────────────────┬─────────────────────┘
                                           │
                                           ▼
                      ┌──────────────────────────────────────────┐
                      │    Multi-Row Parser & Header Detector    │
                      │  - Detects 4-row header metadata         │
                      │  - Filters synthetic / ambiguous blanks  │
                      │  - Isolates data starting at row 5       │
                      └────────────────────┬─────────────────────┘
                                           │
                                           ▼
                      ┌──────────────────────────────────────────┐
                      │     Equus EAFH Transformation Engine     │
                      │  - Field compatibility validator         │
                      │  - Assignment ID Strategy (A, B, C)      │
                      │  - Child entity packer (Addrs/Deps/Tax)  │
                      └──────┬────────────────────────────┬──────┘
                             │                            │
                             ▼                            ▼
        ┌───────────────────────────────┐  ┌───────────────────────────────────┐
        │  Equus Import File (.xlsx)    │  │  Migration Audit Report (.xlsx)  │
        │  - 146 standard EAFH columns  │  │  - Tab 1: Executive Summary      │
        │  - Col A/B: INSERT / UPDATE   │  │  - Tab 2: Column Mappings        │
        │  - Col 1: INSERT once/worker  │  │  - Tab 3: Translations Applied   │
        │  - Clean blanks, no 'null'    │  │  - Tab 4: Warnings & Quarantines │
        └──────────────┬────────────────┘  │  - Tab 5: Entity Breakdown        │
                       │                   └───────────────────────────────────┘
                       ▼
        ┌───────────────────────────────┐
        │  Mock Equus Destination DB    │
        │  - Isolated in-memory adapter │
        │  - Snapshot & rollback audit  │
        │  - Safe Mode writes disabled  │
        └───────────────────────────────┘
```

---

## How It Works

1. **Source Ingestion & Multi-Row Header Alignment:**
   - Ingests Topia exports (`.xlsx`) containing up to 206 historical assignment attributes.
   - Automatically detects 4-row multi-header sheets via `detect_sheet_layout()` and `parse_three_row_workbook()`.
   - Binds canonical human display headers from **Row 4** and commences record evaluation at **Row 5**, suppressing technical rule strings (e.g. `US Date Format`, `EMPLOYEE|BIRTH_DATE`) and blank synthetic headers (`_blank_1`) from contaminating mappings.

2. **Conversion Rules, Semantic Guards & Normalization:**
   - **Dates:** Converted to standardized ISO format (`YYYY-MM-DD`).
   - **Country Codes:** Converted to ISO-3166-1 alpha-3 codes (e.g., `United States` → `USA`).
   - **Compatibility Firewall:** Pre-flight guard blocks invalid transformations (e.g. date transformations applied to country fields or blank headers mapped to targets).
   - **Dropdowns & Dictionaries:** Normalized against Equus reference values (marital status, gender, currency, assignment types).
   - **Null Equivalents:** `"Not Provided"`, `"N/A"`, `"null"`, and whitespace are converted to clean `None` cells.

3. **Parent-Child & Command Semantics:**
   - **`INSERT` Row:** Generated for each assignment (Row 0). Primary child records (Address 1, Contact 1, Dependent 1) nest directly onto this row.
   - **`UPDATE` Rows:** Appended for secondary child entities (Address 2+, Dependent 2+). Sets `Employee Action = "IGNORE"` (Col A) and `Assignment Command = "UPDATE"` (Col B), referencing the parent `Assignment Identifier`.
   - **Worker Demographics Rule:** Col 1 is set to `INSERT` only on the worker's initial assignment; subsequent assignments for that worker automatically specify `IGNORE`.

4. **Deliverables Generated Per Run:**
   - **Equus Import File:** `local_s3/dest_s3/equus/<name>_EQUUS_<timestamp>.xlsx`  
     Formatted according to the 146-column Equus EAFH template with technical instruction rows preserved.
   - **Migration Results Report:** `local_s3/dest_s3/equus/reports/<name>_MAPPING_REPORT_<timestamp>.xlsx`  
     5-tab reconciliation workbook:
     1. *Executive Summary:* Verified source rows, total output records, accepted/rejected counts, and demo execution metrics.
     2. *Column Mappings:* Full source-to-target field dictionary with transformation types and statuses.
     3. *Translations Applied:* Exact dictionary value mappings applied per field.
     4. *Warnings & Issues:* Pre-flight validation warnings, duplicate checks, and unlinked orphan dependent quarantines.
     5. *Entity Breakdown:* Granular counts for employees, assignments, addresses, contacts, and dependents.

---

## Execution Modes

The platform supports three complementary execution interfaces sharing the same pure business logic engine:

### Mode A: Standalone CLI Runner (S3-Compatible Local Batch)
Designed for offline batch execution and CI/CD pipelines without requiring Docker, MongoDB, or browser interaction. Uses local folders standing in for S3 buckets:
- **Input:** `local_s3/source_s3/topia/incoming/*.xlsx`
- **Output:** `local_s3/dest_s3/equus/` and `local_s3/dest_s3/equus/reports/`

### Mode B: Enterprise Web Platform & Demo Mode
Interactive React SPA + FastAPI backend providing real-time data profiling, 5-step workflow stepper, Four-Eyes mapping approvals, and an isolated mock Equus destination (`MockEquusDestination`) for live client walkthroughs.

### Mode C: Event-Driven AWS Serverless Pipeline
Automated cloud ingestion powered by AWS Lambda and S3:
- **Trigger:** S3 `ObjectCreated` events in `topia/incoming/*.xlsx`.
- **Handler:** `lambda/src/handler.py` streams the file, runs the transformation engine, and writes the import and report workbooks to `equus/`.
- **Infrastructure:** `infra/merge_notification.py` non-destructively merges S3 bucket notifications, preserving existing SQS/SNS/EventBridge triggers.

---

## Repository Layout

```
.
├── .github/workflows/ci.yml    # GitHub Actions CI (Ruff lint/format, Pytest on 3.12 & 3.13)
├── app/
│   ├── api/                    # FastAPI REST endpoints (sources, mappings, preview, jobs)
│   ├── core/                   # Security, configuration, and fail-closed target validators
│   ├── services/
│   │   ├── audit.py            # Audit logging service
│   │   ├── preview.py          # Transformation preview engine with warning collection
│   │   ├── profiling.py        # Dataset profiling and header analysis
│   │   ├── transform.py        # Mapping compatibility validation & value transformers
│   │   ├── workbooks.py        # Multi-row layout detection & workbook security
│   │   └── equus/              # Pure Topia -> Equus transformation engine
│   │       ├── __init__.py     # Pipeline coordinator: run_equus_migration_pipeline()
│   │       ├── destination.py  # Isolated Mock Equus Destination engine (INSERT/UPDATE/idempotency)
│   │       ├── generator.py    # openpyxl workbook creators (Equus import + Results Report)
│   │       ├── mapping_config.py# 206-to-146 column mapping rules & value dictionaries
│   │       ├── parser.py       # Multi-row Topia workbook parser
│   │       ├── reconciliation.py# Defensive data quality firewall & accounting metrics
│   │       └── transformer.py  # Assignment key strategies & child row packing
│   └── workers/                # Asynchronous job worker daemon
├── frontend/                   # React 18 + TypeScript + Vite web application
│   ├── src/                    # Components (JobDetails, Stepper, Preflight, Mappings)
│   └── src/test/               # Vitest test suite (17 frontend unit & integration tests)
├── infra/                      # Infrastructure deployment scripts & safety policies
│   ├── deploy.sh               # AWS Lambda & S3 deployment automation
│   ├── merge_notification.py   # Idempotent S3 notification configuration merger
│   ├── s3-notification-filter.json # S3 event filter definition
│   └── source-bucket-policy.json   # TLS 1.2+ and SSE-KMS bucket policy
├── lambda/                     # AWS Lambda deployment package
│   ├── src/                    # Lambda handler and dependency definitions
│   └── template.yaml           # AWS SAM / CloudFormation template
├── local/                      # Standalone CLI tools
│   └── run_local.py            # Local migration runner (simulating S3 bucket workflow)
├── local_s3/                   # Simulated S3 directory tree (incoming exports, generated imports)
├── tests/                      # Automated backend test suite (115 pytest tests)
└── topia_equus_test_workbooks/ # Synthetic test fixtures (clean, numeric IDs, blanks, multi-row)
```

---

## Quick Start & Running Locally

### Prerequisites
- Python 3.12+ (tested through Python 3.13)
- Node.js 18+ (for frontend web UI)

### 1. Set Up Python Environment
```bash
python -m venv .venv

# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Linux / macOS:
source .venv/bin/activate

# Install development dependencies:
pip install -e ".[dev]"
```

### 2. Run Migration via Local CLI Runner
Process a single file or an entire directory of incoming Topia exports:
```bash
# Run a specific test fixture:
python local/run_local.py topia_equus_test_workbooks/01_valid_basic.xlsx

# Or process all workbooks placed in the incoming directory:
python local/run_local.py
```
Outputs are immediately written to:
- `local_s3/dest_s3/equus/01_valid_basic_EQUUS_<timestamp>.xlsx`
- `local_s3/dest_s3/equus/reports/01_valid_basic_MAPPING_REPORT_<timestamp>.xlsx`

### 3. Run Automated Tests
```bash
# Backend test suite (115 tests):
python -m pytest -q

# Code formatting & linting checks:
ruff check .
ruff format --check .

# Frontend test suite (17 tests):
cd frontend && npm test -- --run
```

### 4. Run Enterprise Web Platform
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

- **Default Policy:** `EQUUS_WRITES_DISABLED=true` (Outbound writes to live Equus production systems are strictly blocked by policy).
- **Demo Write Configuration:**
  ```bash
  EQUUS_TARGET="mock"
  MIGRATION_DEMO_WRITES_ENABLED="true"
  ```
- **Fail-Closed Security Guarantee:** Attempting to enable demo writes against any target other than `"mock"` raises an immediate error (`PermissionError` / HTTP 403 `LIVE_WRITES_DISABLED` or HTTP 422 `INVALID_DEMO_TARGET`). Live Equus API calls are structurally blocked in demo mode.

---

## Client Mapping Decisions & Configuration

The platform addresses all key client specifications:

1. **Multi-Row Header Detection:**  
   Header detection automatically reads canonical display headers from Row 4, making ingestion fully independent of visual cell colors and ignoring technical rule annotations.
2. **Assignment Identifier Strategies:**  
   Configurable via `--strategy`:
   - `Option A` (`EMPLOYEE_NUMBER`): Client default using Employee Number base (`<EMP_NUM>` / `<EMP_NUM>-A2`).
   - `Option B` (`TOPIA_ID`): Authoritative Topia Assignment ID (`<TOPIA_ID>`).
   - `Option C` (`HYBRID`): Combination format (`<EMP_NUM>_<TOPIA_ID>`).
3. **Resource Fields (`RESOURCE_MAP`):**  
   Lookup dictionary configured in `mapping_config.py`; unmapped consultants log clear warnings in Tab 4 rather than halting execution.
4. **Address Parsing:**  
   Decomposes structured address blocks into street, city, postal code, and ISO-3 country codes.
5. **Dependent Data Linkage:**  
   Embedded dependents on assignment rows link automatically; orphan dependents lacking an employee key are safely quarantined in Tab 4 (`UNLINKED_DEPENDENT`) without guessing parentage.
6. **Confirmed Defaults:**  
   Effective dates default to assignment start date; International Assignment derives from country mismatch; clean blanks for missing optional values.
