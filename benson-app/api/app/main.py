from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from .ai_routes import router as ai_router
from .asset_routes import router as asset_router
from .config import get_settings
from .customer_routes import router as customer_router
from .estimate_routes import router as estimate_router
from .lead_routes import router as lead_router
from .job_routes import router as job_router
from .onboarding_routes import router as onboarding_router
from .storage import operations_store
from .system_routes import router as system_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await run_in_threadpool(
        operations_store(settings.resolved_database_url()).initialize_schema
    )
    yield


app = FastAPI(
    title="Benson Operations API",
    version="0.2.0",
    description="Focused residential contractor operations for Benson Home Solutions.",
    lifespan=lifespan,
)
app.include_router(system_router)
app.include_router(customer_router)
app.include_router(estimate_router)
app.include_router(job_router)
app.include_router(onboarding_router)
app.include_router(lead_router)
app.include_router(ai_router)
app.include_router(asset_router)

_web_dist_path = get_settings().web_dist_path
if _web_dist_path is not None and _web_dist_path.is_dir():
    app.mount("/", StaticFiles(directory=_web_dist_path, html=True), name="web")
