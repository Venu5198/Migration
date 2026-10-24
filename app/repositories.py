import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import AsyncMongoClient, ReturnDocument

from app.schemas import JobStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryRepository:
    def __init__(self) -> None:
        self.sources: dict[str, dict[str, Any]] = {}
        self.mappings: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.audits: list[dict[str, Any]] = []
        self.mapping_versions: dict[tuple[str, int], dict[str, Any]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_indexes(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health(self) -> bool:
        return False

    async def put_source(self, source: dict[str, Any]) -> None:
        self.sources[source["source_id"]] = source

    async def get_source(self, source_id: str) -> dict[str, Any] | None:
        return self.sources.get(source_id)

    async def list_sources(self) -> list[dict[str, Any]]:
        return sorted(self.sources.values(), key=lambda item: item["created_at"], reverse=True)

    async def add_audit(self, event: dict[str, Any]) -> None:
        self.audits.append(event)

    async def list_audit(self, entity_id: str) -> list[dict[str, Any]]:
        return [item for item in self.audits if item.get("entity_id") == entity_id]

    async def list_audit_page(
        self, entity_id: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        events = [
            item for item in self.audits if entity_id is None or item.get("entity_id") == entity_id
        ]
        events.sort(key=lambda item: item["timestamp"], reverse=True)
        return events[skip : skip + limit], len(events)

    async def put_mapping(self, mapping: dict[str, Any]) -> None:
        self.mappings[mapping["mapping_id"]] = mapping

    async def put_mapping_version(self, mapping: dict[str, Any]) -> None:
        self.mapping_versions[(mapping["mapping_id"], mapping["version"])] = mapping.copy()

    async def list_mapping_versions(self, mapping_id: str) -> list[dict[str, Any]]:
        versions = [value for (key, _), value in self.mapping_versions.items() if key == mapping_id]
        versions.sort(key=lambda item: item["version"], reverse=True)
        return versions

    async def put_report(self, report: dict[str, Any]) -> None:
        self.reports[report["report_id"]] = report

    async def get_mapping(self, mapping_id: str) -> dict[str, Any] | None:
        return self.mappings.get(mapping_id)

    async def list_mappings(self, source_id: str) -> list[dict[str, Any]]:
        return [item for item in self.mappings.values() if item["source_id"] == source_id]

    async def put_job(self, job: dict[str, Any]) -> None:
        self.jobs[job["job_id"]] = job

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    async def list_jobs(
        self, kind: str | None = None, source_id: str | None = None
    ) -> list[dict[str, Any]]:
        jobs = list(self.jobs.values())
        if kind:
            jobs = [j for j in jobs if j.get("kind") == kind]
        if source_id:
            jobs = [j for j in jobs if j.get("source_id") == source_id]
        jobs.sort(key=lambda item: item["created_at"], reverse=True)
        return jobs

    async def request_cancel(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job["cancellation_requested"] = True
        if job["status"] in {JobStatus.PENDING, JobStatus.QUEUED, JobStatus.READY}:
            job["status"] = JobStatus.CANCELLED
        job["updated_at"] = utcnow()

    async def claim_job(self, worker_id: str, max_attempts: int = 3) -> dict[str, Any] | None:
        async with self._lock:
            now = utcnow()
            for job in self.jobs.values():
                if (
                    job["status"] == JobStatus.RUNNING
                    and job.get("lease_expires_at", now) <= now
                    and job.get("attempts", 0) >= max_attempts
                ):
                    job.update(
                        status=JobStatus.FAILED,
                        failure_code="MAX_ATTEMPTS_EXCEEDED",
                        lease_owner=None,
                        lease_expires_at=None,
                        updated_at=now,
                    )
            candidates = [
                job
                for job in self.jobs.values()
                if not job.get("cancellation_requested", False)
                and job.get("attempts", 0) < max_attempts
                and (
                    job["status"] in {JobStatus.PENDING, JobStatus.QUEUED}
                    or (
                        job["status"] == JobStatus.RUNNING
                        and job.get("lease_expires_at", now) <= now
                    )
                )
            ]
            if not candidates:
                return None
            job = min(candidates, key=lambda item: item["created_at"])
            job.update(
                status=JobStatus.RUNNING,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(minutes=5),
                attempts=job["attempts"] + 1,
                updated_at=now,
            )
            return job.copy()

    async def finish_job(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        failure_code: str | None = None,
    ) -> None:
        job = self.jobs[job_id]
        job.update(
            status=status,
            result=result,
            failure_code=failure_code,
            updated_at=utcnow(),
            lease_owner=None,
            lease_expires_at=None,
            progress=100
            if status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS}
            else job["progress"],
        )


class MongoRepository:
    def __init__(self, uri: str, db_name: str | None = None) -> None:
        self.client = AsyncMongoClient(uri)
        if db_name:
            self.db = self.client.get_database(db_name)
        else:
            try:
                self.db = self.client.get_default_database()
            except Exception:
                self.db = self.client.get_database("migration")

    async def create_indexes(self) -> None:
        await self.db.sources.create_index("source_id", unique=True)
        await self.db.migration_jobs.create_index(
            [("status", 1), ("lease_expires_at", 1), ("created_at", 1)]
        )
        await self.db.mappings.create_index("mapping_id", unique=True)
        await self.db.mapping_versions.create_index(
            [("mapping_id", 1), ("version", -1)], unique=True
        )
        await self.db.audit_events.create_index([("entity_id", 1), ("timestamp", -1)])
        await self.db.audit_events.create_index([("job_id", 1), ("timestamp", -1)])

    async def close(self) -> None:
        await self.client.close()

    async def health(self) -> bool:
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False

    async def put_source(self, source: dict) -> None:
        await self.db.sources.replace_one({"source_id": source["source_id"]}, source, upsert=True)

    async def get_source(self, source_id: str) -> dict | None:
        return await self.db.sources.find_one({"source_id": source_id}, {"_id": 0})

    async def list_sources(self) -> list[dict]:
        return [item async for item in self.db.sources.find({}, {"_id": 0}).sort("created_at", -1)]

    async def add_audit(self, event: dict) -> None:
        await self.db.audit_events.insert_one(event)

    async def list_audit(self, entity_id: str) -> list[dict]:
        return [
            item
            async for item in self.db.audit_events.find({"entity_id": entity_id}, {"_id": 0}).sort(
                "timestamp", -1
            )
        ]

    async def list_audit_page(
        self, entity_id: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        query = {"entity_id": entity_id} if entity_id else {}
        total = await self.db.audit_events.count_documents(query)
        events = [
            item
            async for item in self.db.audit_events.find(query, {"_id": 0})
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        ]
        return events, total

    async def put_mapping_version(self, mapping: dict) -> None:
        await self.db.mapping_versions.replace_one(
            {"mapping_id": mapping["mapping_id"], "version": mapping["version"]},
            mapping,
            upsert=True,
        )

    async def list_mapping_versions(self, mapping_id: str) -> list[dict]:
        return [
            item
            async for item in self.db.mapping_versions.find(
                {"mapping_id": mapping_id}, {"_id": 0}
            ).sort("version", -1)
        ]

    async def put_report(self, report: dict) -> None:
        await self.db.report_metadata.replace_one(
            {"report_id": report["report_id"]}, report, upsert=True
        )

    async def put_mapping(self, mapping: dict) -> None:
        await self.db.mappings.replace_one(
            {"mapping_id": mapping["mapping_id"]}, mapping, upsert=True
        )

    async def get_mapping(self, mapping_id: str) -> dict | None:
        return await self.db.mappings.find_one({"mapping_id": mapping_id}, {"_id": 0})

    async def list_mappings(self, source_id: str) -> list[dict]:
        return [item async for item in self.db.mappings.find({"source_id": source_id}, {"_id": 0})]

    async def put_job(self, job: dict) -> None:
        await self.db.migration_jobs.replace_one({"job_id": job["job_id"]}, job, upsert=True)

    async def get_job(self, job_id: str) -> dict | None:
        return await self.db.migration_jobs.find_one({"job_id": job_id}, {"_id": 0})

    async def list_jobs(
        self, kind: str | None = None, source_id: str | None = None
    ) -> list[dict]:
        query: dict[str, Any] = {}
        if kind:
            query["kind"] = kind
        if source_id:
            query["source_id"] = source_id
        return [
            item
            async for item in self.db.migration_jobs.find(query, {"_id": 0}).sort("created_at", -1)
        ]

    async def request_cancel(self, job_id: str) -> None:
        await self.db.migration_jobs.update_one(
            {
                "job_id": job_id,
                "status": {
                    "$nin": [JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS, JobStatus.FAILED]
                },
            },
            {"$set": {"cancellation_requested": True, "updated_at": utcnow()}},
        )
        await self.db.migration_jobs.update_one(
            {
                "job_id": job_id,
                "status": {"$in": [JobStatus.PENDING, JobStatus.QUEUED, JobStatus.READY]},
            },
            {"$set": {"status": JobStatus.CANCELLED}},
        )

    async def claim_job(self, worker_id: str, max_attempts: int = 3) -> dict | None:
        now = utcnow()
        await self.db.migration_jobs.update_many(
            {
                "status": JobStatus.RUNNING,
                "lease_expires_at": {"$lte": now},
                "attempts": {"$gte": max_attempts},
            },
            {
                "$set": {
                    "status": JobStatus.FAILED,
                    "failure_code": "MAX_ATTEMPTS_EXCEEDED",
                    "updated_at": now,
                    "lease_owner": None,
                    "lease_expires_at": None,
                }
            },
        )
        return await self.db.migration_jobs.find_one_and_update(
            {
                "attempts": {"$lt": max_attempts},
                "cancellation_requested": {"$ne": True},
                "$or": [
                    {"status": {"$in": [JobStatus.PENDING, JobStatus.QUEUED]}},
                    {"status": JobStatus.RUNNING, "lease_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "status": JobStatus.RUNNING,
                    "lease_owner": worker_id,
                    "lease_expires_at": now + timedelta(minutes=5),
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    async def finish_job(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        failure_code: str | None = None,
    ) -> None:
        await self.db.migration_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": status,
                    "result": result,
                    "failure_code": failure_code,
                    "updated_at": utcnow(),
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "progress": 100
                    if status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS}
                    else 0,
                }
            },
        )
