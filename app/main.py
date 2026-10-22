from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, jobs, mappings, sources
from app.core.config import settings
from app.core.errors import DomainError, domain_error_handler
from app.repositories import MemoryRepository, MongoRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings.validate_production()
        settings.require_auth()
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    app.state.repository = (
        MongoRepository(settings.mongodb_uri) if settings.mongodb_uri else MemoryRepository()
    )
    if settings.is_production() and not await app.state.repository.health():
        raise RuntimeError("API startup failed: MongoDB is unreachable in production mode.")
    await app.state.repository.create_indexes()
    yield
    await app.state.repository.close()


app = FastAPI(title="Migration API", version="0.1.0", lifespan=lifespan)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
app.add_exception_handler(DomainError, domain_error_handler)
app.include_router(sources.router)
app.include_router(mappings.router)
app.include_router(jobs.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    mongo_ok = await app.state.repository.health()
    return {
        "status": "ok" if mongo_ok else "degraded",
        "database": "connected" if mongo_ok else "not_configured_or_unavailable",
        "equus_writes": "disabled",
    }


@app.get("/live")
async def live():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    mongo_ok = await app.state.repository.health()
    if settings.is_production():
        if not mongo_ok:
            raise HTTPException(
                503,
                detail={
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "MongoDB is required and unavailable in production mode.",
                },
            )
        return {"status": "ready", "database": "connected"}
    if settings.mongodb_uri and not mongo_ok:
        raise HTTPException(
            503, detail={"code": "DATABASE_UNAVAILABLE", "message": "MongoDB is unavailable."}
        )
    return {
        "status": "ready",
        "database": "connected" if mongo_ok else "development_fallback",
    }
