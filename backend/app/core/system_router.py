# OpenConstructionERP - DataDrivenConstruction (DDC)
# CWICR Cost Database Engine · CAD2DATA Pipeline
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
# AGPL-3.0 License · DDC-CWICR-OE-2026
"""System routes for health checks and basic information."""

from fastapi import APIRouter
from app.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/info")
async def get_info():
    """Get basic application information."""
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "description": "Open-source modular platform for construction cost estimation",
    }