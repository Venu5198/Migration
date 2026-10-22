"""Opt-in tests: only run against MIGRATION_TEST_MONGODB_URI, never production."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories import MongoRepository
from app.schemas import JobStatus


@pytest.mark.asyncio
async def test_mongo_indexes_and_health():
    uri = os.getenv("MIGRATION_TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set MIGRATION_TEST_MONGODB_URI to an isolated disposable MongoDB database")
    repo = MongoRepository(uri)
    try:
        assert await repo.health()
        await repo.create_indexes()
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_mongo_full_repository_lifecycle():
    uri = os.getenv("MIGRATION_TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set MIGRATION_TEST_MONGODB_URI to an isolated disposable MongoDB database")
    repo = MongoRepository(uri)
    try:
        await repo.create_indexes()
        source_id = str(uuid4())
        now = datetime.now(UTC)

        # 1. Source lifecycle
        source = {
            "source_id": source_id,
            "original_filename": "test.xlsx",
            "storage_path": "/tmp/test.xlsx",
            "sha256": "fakehash123",
            "created_at": now,
            "sheets": [{"name": "Assignments", "max_row": 10, "max_column": 3, "headers": ["A"]}],
        }
        await repo.put_source(source)
        retrieved_source = await repo.get_source(source_id)
        assert retrieved_source is not None
        assert retrieved_source["sha256"] == "fakehash123"

        sources_list = await repo.list_sources()
        assert any(s["source_id"] == source_id for s in sources_list)

        # 2. Mapping & versioning lifecycle
        mapping_id = str(uuid4())
        mapping = {
            "mapping_id": mapping_id,
            "source_id": source_id,
            "source_entity": "employee",
            "source_sheet": "Assignments",
            "source_field": "A",
            "target_entity": "employee",
            "target_field": "emp_id",
            "mapping_type": "direct",
            "status": "proposed",
            "version": 1,
            "created_at": now,
        }
        await repo.put_mapping(mapping)
        await repo.put_mapping_version(mapping.copy())

        retrieved_map = await repo.get_mapping(mapping_id)
        assert retrieved_map is not None
        assert retrieved_map["version"] == 1

        versions = await repo.list_mapping_versions(mapping_id)
        assert len(versions) == 1
        assert versions[0]["version"] == 1

        # 3. Job claiming, leasing, and completion
        job_id = str(uuid4())
        job = {
            "job_id": job_id,
            "kind": "profile",
            "source_id": source_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "result": None,
            "failure_code": None,
            "cancellation_requested": False,
        }
        await repo.put_job(job)

        claimed = await repo.claim_job("test-worker-1", max_attempts=3)
        assert claimed is not None
        assert claimed["job_id"] == job_id
        assert claimed["status"] == JobStatus.RUNNING
        assert claimed["attempts"] == 1

        await repo.finish_job(
            job_id,
            JobStatus.COMPLETED,
            result={"sheets": [{"name": "Assignments", "populated_rows": 5}]},
        )
        finished = await repo.get_job(job_id)
        assert finished["status"] == JobStatus.COMPLETED
        assert finished["progress"] == 100
        assert finished["result"]["sheets"][0]["populated_rows"] == 5

        # 4. Audit events and pagination
        entity_id = str(uuid4())
        await repo.add_audit(
            {
                "event_id": str(uuid4()),
                "timestamp": datetime.now(UTC),
                "action": "source.uploaded",
                "entity_id": entity_id,
                "actor": "tester",
                "job_id": None,
                "correlation_id": None,
                "metadata": {"sha256": "digest123"},
            }
        )
        audit_records = await repo.list_audit(entity_id)
        assert len(audit_records) == 1
        assert audit_records[0]["action"] == "source.uploaded"

        paged_events, total = await repo.list_audit_page(entity_id, 0, 10)
        assert total == 1
        assert len(paged_events) == 1

        # 5. Report metadata
        report_id = str(uuid4())
        await repo.put_report(
            {
                "report_id": report_id,
                "job_id": job_id,
                "report_type": "preview_csv",
                "generated_at": datetime.now(UTC),
                "workbook_digest": "fakehash123",
            }
        )
        # Verify isolation
        assert "test" in repo.db.name.lower()
        assert repo.db.name != "migration"
    finally:
        if "test" in repo.db.name.lower():
            await repo.client.drop_database(repo.db.name)
        await repo.close()
