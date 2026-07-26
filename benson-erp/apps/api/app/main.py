from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.core.health import check_readiness
from app.core.observability import (
    RequestObservabilityMiddleware,
    configure_logging,
    configure_tracing,
    metrics_response,
)
from app.core.spa import mount_spa
from app.modules.crm.routes import router as crm_router
from app.modules.estimating.routes import router as estimating_router
from app.modules.federal_labor.routes import router as federal_labor_router
from app.modules.payroll.routes import router as payroll_router
from app.modules.people.routes import router as people_router
from app.modules.platform.auth_routes import router as auth_router
from app.modules.projects.routes import router as projects_router
from app.modules.scheduling.routes import router as scheduling_router
from app.modules.timekeeping.routes import router as timekeeping_router

configure_logging(settings)

app = FastAPI(
    title="Benson Construction ERP API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
)
app.state.settings = settings
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_headers=[
        "Authorization",
        "Content-Type",
        "If-Match",
        "X-Correlation-ID",
        "X-CSRF-Token",
    ],
    allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT"],
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    expose_headers=["X-Correlation-ID"],
)
app.add_middleware(RequestObservabilityMiddleware)
app.include_router(crm_router, prefix="/api/v1")
app.include_router(estimating_router, prefix="/api/v1")
app.include_router(federal_labor_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(people_router, prefix="/api/v1")
app.include_router(payroll_router, prefix="/api/v1")
app.include_router(scheduling_router, prefix="/api/v1")
app.include_router(timekeeping_router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    result = await check_readiness(engine, settings)
    return JSONResponse(
        status_code=200 if result.ready else 503,
        content={
            "status": "ready" if result.ready else "not_ready",
            "checks": result.checks,
        },
    )


if settings.metrics_enabled:
    app.add_api_route(
        "/metrics",
        metrics_response,
        methods=["GET"],
        include_in_schema=False,
    )


@app.get("/api/v1", tags=["platform"])
async def api_root() -> dict[str, str]:
    return {"name": app.title, "version": app.version}


configure_tracing(app, engine, settings)
mount_spa(app, settings.web_dist_path)
