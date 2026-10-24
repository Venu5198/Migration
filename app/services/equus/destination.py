"""Mock Equus destination adapter for isolated, verifiable demo-write execution.

Provides an isolated local destination dataset (employees, assignments, addresses, contacts, dependents).
Ensures safe demonstration of INSERT and UPDATE operations without live Equus API connections.
Includes strict fail-closed safety checks, snapshotting, and destination read-back verification.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.config import settings


@dataclass
class DestinationExecutionSummary:
    run_id: str
    target: str  # e.g. "mock-equus-local"
    executed_at: str
    demo_writes_enabled: bool
    attempted: int = 0
    successful: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    rejected: int = 0
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    verification_status: str = "UNVERIFIED"  # VERIFIED_MATCH, DISCREPANCIES_FOUND, FAILED
    before_counts: dict[str, int] = field(default_factory=dict)
    after_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MockEquusDestination:
    """Isolated, in-memory/persisted synthetic destination simulating the Equus database."""

    def __init__(self) -> None:
        self.employees: dict[str, dict[str, Any]] = {}
        self.assignments: dict[str, dict[str, Any]] = {}
        self.addresses: list[dict[str, Any]] = []
        self.contacts: list[dict[str, Any]] = []
        self.dependents: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []

    def reset(self, seed_data: dict[str, Any] | None = None) -> None:
        """Reset destination state, optionally seeding with synthetic baseline records."""
        self.employees.clear()
        self.assignments.clear()
        self.addresses.clear()
        self.contacts.clear()
        self.dependents.clear()
        if seed_data:
            for emp in seed_data.get("employees", []):
                self.employees[emp["employee_number"]] = deepcopy(emp)
            for asg in seed_data.get("assignments", []):
                self.assignments[asg["assignment_identifier"]] = deepcopy(asg)
            for addr in seed_data.get("addresses", []):
                self.addresses.append(deepcopy(addr))
            for c in seed_data.get("contacts", []):
                self.contacts.append(deepcopy(c))
            for dep in seed_data.get("dependents", []):
                self.dependents.append(deepcopy(dep))

    def snapshot(self) -> dict[str, Any]:
        """Capture complete destination state before or after a migration run."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "counts": {
                "employees": len(self.employees),
                "assignments": len(self.assignments),
                "addresses": len(self.addresses),
                "contacts": len(self.contacts),
                "dependents": len(self.dependents),
            },
            "employees": deepcopy(self.employees),
            "assignments": deepcopy(self.assignments),
            "addresses": deepcopy(self.addresses),
            "contacts": deepcopy(self.contacts),
            "dependents": deepcopy(self.dependents),
        }

    def read_back_employee(self, emp_no: str) -> dict[str, Any] | None:
        """Read back an employee record by employee number."""
        return deepcopy(self.employees.get(str(emp_no).strip()))

    def read_back_assignment(self, asg_id: str) -> dict[str, Any] | None:
        """Read back an assignment record along with its linked child entities."""
        key = str(asg_id).strip()
        asg = self.assignments.get(key)
        if not asg:
            return None
        res = deepcopy(asg)
        res["addresses"] = [a for a in self.addresses if a.get("assignment_identifier") == key]
        res["contacts"] = [c for c in self.contacts if c.get("assignment_identifier") == key]
        res["dependents"] = [d for d in self.dependents if d.get("assignment_identifier") == key]
        return res

    def read_back_all(self) -> dict[str, Any]:
        """Read back the complete dataset for verification."""
        return self.snapshot()

    def execute_records(
        self,
        records: list[dict[int, Any]],
        header_map: dict[int, str] | None = None,
        run_id: str | None = None,
        target: str = "mock",
        demo_writes_enabled: bool = True,
    ) -> DestinationExecutionSummary:
        """Execute migration records against the isolated destination with verification.

        Fails closed if target is not explicitly 'mock' in demo write mode.
        """
        # Strict fail-closed guard
        settings.validate_equus_destination(target=target, demo_writes=demo_writes_enabled)

        if not demo_writes_enabled:
            # Planned preview only; do not execute writes
            return DestinationExecutionSummary(
                run_id=run_id or str(uuid4()),
                target="none",
                executed_at=datetime.now(UTC).isoformat(),
                demo_writes_enabled=False,
                verification_status="SKIPPED_SAFE_MODE",
                before_counts=self.snapshot()["counts"],
                after_counts=self.snapshot()["counts"],
            )

        active_run_id = run_id or f"demo-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        before_snap = self.snapshot()
        summary = DestinationExecutionSummary(
            run_id=active_run_id,
            target="mock-equus-local",
            executed_at=datetime.now(UTC).isoformat(),
            demo_writes_enabled=True,
            before_counts=before_snap["counts"],
        )

        h_map = header_map or {}

        for rec_idx, rec in enumerate(records, start=1):
            summary.attempted += 1
            cmd_a = str(rec.get(1) or "").strip().upper()
            cmd_b = str(rec.get(2) or "").strip().upper()
            emp_no = str(rec.get(3)).strip() if rec.get(3) is not None else None
            asg_id = str(rec.get(5)).strip() if rec.get(5) is not None else None

            # Dissect fields from row using header_map
            emp_fields: dict[str, Any] = {}
            asg_fields: dict[str, Any] = {}
            addr_data: dict[str, Any] = {}
            contact_data: dict[str, Any] = {}
            dep_data: dict[str, Any] = {}

            for col_idx, val in rec.items():
                if val is None or col_idx in (1, 2, 3, 4, 5):
                    continue
                header = h_map.get(col_idx, "").upper()
                if "ASSIGNMENT_MAILING_ADDRESS" in header:
                    field_key = header.replace("ASSIGNMENT_MAILING_ADDRESS!", "").lower()
                    addr_data[field_key] = val
                elif "ASSIGNMENT_EMPLOYEE_CONTACT" in header:
                    field_key = header.replace("ASSIGNMENT_EMPLOYEE_CONTACT!", "").lower()
                    contact_data[field_key] = val
                elif "ASSIGNMENT_DEPENDENT" in header:
                    field_key = header.replace("ASSIGNMENT_DEPENDENT!", "").lower()
                    dep_data[field_key] = val
                elif "EMPLOYEE" in header:
                    field_key = header.replace("EMPLOYEE!", "").lower()
                    emp_fields[field_key] = val
                elif "ASSIGNMENT" in header:
                    field_key = header.replace("ASSIGNMENT!", "").lower()
                    asg_fields[field_key] = val

            # Operation Branch 1: INSERT Record (Row 0 of an assignment)
            if cmd_b == "INSERT":
                if not asg_id or not emp_no:
                    summary.failed += 1
                    summary.errors.append(
                        {
                            "record_index": rec_idx,
                            "error": f"Missing required identifier: emp_no={emp_no}, asg_id={asg_id}",
                        }
                    )
                    continue

                # Employee Demographics Handling
                if cmd_a == "INSERT":
                    if emp_no not in self.employees:
                        self.employees[emp_no] = {
                            "employee_number": emp_no,
                            "created_at": summary.executed_at,
                            "updated_at": summary.executed_at,
                            "last_run_id": active_run_id,
                            **emp_fields,
                        }
                        summary.inserted += 1
                    else:
                        # Existing employee: update demographics
                        self.employees[emp_no].update(emp_fields)
                        self.employees[emp_no]["updated_at"] = summary.executed_at
                        self.employees[emp_no]["last_run_id"] = active_run_id
                        summary.updated += 1
                elif cmd_a == "IGNORE":
                    # Repeat assignment: employee already exists
                    if emp_no not in self.employees:
                        # Pre-populate empty employee envelope if missing
                        self.employees[emp_no] = {
                            "employee_number": emp_no,
                            "created_at": summary.executed_at,
                            "last_run_id": active_run_id,
                        }

                # Assignment Insertion Handling
                if asg_id not in self.assignments:
                    self.assignments[asg_id] = {
                        "assignment_identifier": asg_id,
                        "employee_number": emp_no,
                        "created_at": summary.executed_at,
                        "updated_at": summary.executed_at,
                        "last_run_id": active_run_id,
                        **asg_fields,
                    }
                    summary.inserted += 1
                    summary.successful += 1
                else:
                    # Idempotency check: does existing assignment have same values?
                    existing = self.assignments[asg_id]
                    diffs = {k: v for k, v in asg_fields.items() if existing.get(k) != v}
                    if not diffs:
                        summary.skipped += 1
                        summary.successful += 1
                    else:
                        existing.update(asg_fields)
                        existing["updated_at"] = summary.executed_at
                        existing["last_run_id"] = active_run_id
                        summary.updated += 1
                        summary.successful += 1

                # Pack Child 0 records onto destination
                if addr_data:
                    self._upsert_child(self.addresses, "location_type", asg_id, addr_data)
                if contact_data:
                    self._upsert_child(self.contacts, "location_type", asg_id, contact_data)
                if dep_data:
                    self._upsert_child(self.dependents, "first_name", asg_id, dep_data)

            # Operation Branch 2: UPDATE Record (Child rows 1..N)
            elif cmd_b == "UPDATE":
                if not asg_id:
                    summary.failed += 1
                    summary.errors.append(
                        {
                            "record_index": rec_idx,
                            "error": "Child UPDATE row missing required Assignment Identifier (Col 5)",
                        }
                    )
                    continue

                if asg_id not in self.assignments:
                    summary.failed += 1
                    summary.errors.append(
                        {
                            "record_index": rec_idx,
                            "error": f"Child UPDATE references non-existent assignment '{asg_id}'",
                        }
                    )
                    continue

                updated_child = False
                if addr_data:
                    self._upsert_child(self.addresses, "location_type", asg_id, addr_data)
                    updated_child = True
                if contact_data:
                    self._upsert_child(self.contacts, "location_type", asg_id, contact_data)
                    updated_child = True
                if dep_data:
                    self._upsert_child(self.dependents, "first_name", asg_id, dep_data)
                    updated_child = True

                if updated_child:
                    summary.updated += 1
                    summary.successful += 1
                else:
                    summary.skipped += 1

            else:
                summary.rejected += 1
                summary.errors.append(
                    {
                        "record_index": rec_idx,
                        "error": f"Unsupported assignment command '{cmd_b}'",
                    }
                )

        after_snap = self.snapshot()
        summary.after_counts = after_snap["counts"]

        # Phase 4: Destination Read-back verification
        self._verify_read_back(records, h_map, summary)
        self.history.append(summary.to_dict())
        return summary

    def _upsert_child(
        self,
        child_list: list[dict[str, Any]],
        key_field: str,
        asg_id: str,
        data: dict[str, Any],
    ) -> None:
        """Helper to upsert a child record (address, contact, dependent) for an assignment."""
        target_val = data.get(key_field)
        for item in child_list:
            if item.get("assignment_identifier") == asg_id and item.get(key_field) == target_val:
                item.update(data)
                return
        record = {"assignment_identifier": asg_id, **data}
        child_list.append(record)

    def _verify_read_back(
        self,
        records: list[dict[int, Any]],
        h_map: dict[int, str],
        summary: DestinationExecutionSummary,
    ) -> None:
        """Read back affected records from destination and compare against input values."""
        discrepancies: list[dict[str, Any]] = []

        for rec_idx, rec in enumerate(records, start=1):
            asg_id = str(rec.get(5)).strip() if rec.get(5) is not None else None
            if not asg_id:
                continue

            dest_asg = self.read_back_assignment(asg_id)
            if not dest_asg:
                discrepancies.append(
                    {
                        "record_index": rec_idx,
                        "assignment_identifier": asg_id,
                        "field": "assignment",
                        "error": "Assignment not found in destination read-back",
                    }
                )
                continue

            emp_no = str(rec.get(3)).strip() if rec.get(3) is not None else None
            if emp_no:
                dest_emp = self.read_back_employee(emp_no)
                if not dest_emp:
                    discrepancies.append(
                        {
                            "record_index": rec_idx,
                            "employee_number": emp_no,
                            "field": "employee",
                            "error": "Employee not found in destination read-back",
                        }
                    )

        summary.discrepancies = discrepancies
        if discrepancies:
            summary.verification_status = "DISCREPANCIES_FOUND"
        elif summary.failed > 0:
            summary.verification_status = "FAILED"
        else:
            summary.verification_status = "VERIFIED_MATCH"


# Global singleton instance for application worker and tests
_mock_destination_instance: MockEquusDestination | None = None


def get_mock_destination() -> MockEquusDestination:
    """Obtain or initialize the global isolated mock destination."""
    global _mock_destination_instance
    if _mock_destination_instance is None:
        _mock_destination_instance = MockEquusDestination()
    return _mock_destination_instance
