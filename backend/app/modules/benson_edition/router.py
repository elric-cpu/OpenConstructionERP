from fastapi import APIRouter

from app.config import get_settings
from app.core.edition import BENSON_REGION, supported_locale_codes
from app.modules.benson_edition.capabilities import CAPABILITIES
from app.modules.benson_workers.providers import provider_status

router = APIRouter()


@router.get("/")
async def edition_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "edition": settings.edition,
        "default_locale": settings.default_locale,
        "supported_locales": sorted(supported_locale_codes()),
        "default_region": settings.default_region or BENSON_REGION,
        "project_context_required": ["county", "local_jurisdiction", "timezone"],
        "capabilities": CAPABILITIES,
        "providers": provider_status(settings),
    }
