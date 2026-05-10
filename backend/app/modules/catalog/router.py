"""‌⁠‍Catalog API routes.

The catalog stores **resources** — single-input items (one material, one
labour rate, one machine, etc.) with one price per region. Resources do
not have a material/labour/equipment breakdown because each resource
*already is* one of those — the kind is in ``resource_type``.

Resources are referenced by **cost positions** (work compositions) in
``oe_costs_item``, exposed at ``/api/v1/costs/``. A position's
``components[]`` array names the resources it consumes by ``code`` and
adds quantity / unit-rate / cost. So:

    /api/v1/costs/         — work positions (≈55k canonical, more with
                             regional price variants). The "work items"
                             you see referenced in legacy CSV columns
                             *are* these.
    /api/v1/catalog/       — leaf resources with prices. Each maps to
                             zero or more cost positions via the
                             ``components[].code`` field.

Use ``/api/v1/catalog/{resource_id}/used-by/`` to walk the relation in
the resource→positions direction (the inverse of ``components[]``).

Endpoints:
    GET  /           -- Search/list catalog resources (public, query params)
    GET  /stats      -- Counts by type and category
    GET  /regions    -- List loaded catalog regions with counts
    POST /import/{region} -- Download catalog from GitHub and import
    DELETE /region/{region} -- Remove all resources for a region
    PATCH /adjust-prices -- Bulk price adjustment by factor
    GET  /{resource_id}            -- Get single resource by ID
    GET  /{resource_id}/used-by/   -- Cost positions that reference this resource
    POST /           -- Create a custom resource (auth required)
    POST /extract    -- Extract resources from cost items (admin)
"""

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String

from app.dependencies import CurrentUserId, RequirePermission, SessionDep
from app.modules.catalog.schemas import (
    CatalogResourceCreate,
    CatalogResourceResponse,
    CatalogSearchResponse,
    CatalogStatsResponse,
)
from app.modules.catalog.service import CatalogResourceService

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> CatalogResourceService:
    return CatalogResourceService(session)


# ── Region-to-GitHub mapping ─────────────────────────────────────────────

REGION_MAP: dict[str, str] = {
    "AR_DUBAI": "AR___DDC_CWICR",
    "DE_BERLIN": "DE___DDC_CWICR",
    "ENG_TORONTO": "EN___DDC_CWICR",
    "SP_BARCELONA": "ES___DDC_CWICR",
    "FR_PARIS": "FR___DDC_CWICR",
    "HI_MUMBAI": "HI___DDC_CWICR",
    "PT_SAOPAULO": "PT___DDC_CWICR",
    "RU_STPETERSBURG": "RU___DDC_CWICR",
    "UK_GBP": "UK___DDC_CWICR",
    "USA_USD": "US___DDC_CWICR",
    "ZH_SHANGHAI": "ZH___DDC_CWICR",
}

_GITHUB_BASE = "https://raw.githubusercontent.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR/main"


# ── Import from GitHub ───────────────────────────────────────────────────


@router.post("/import/{region}")
async def import_catalog_from_github(
    region: str,
    session: SessionDep,
    _user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("catalog.create")),
) -> dict[str, Any]:
    """‌⁠‍Download resource catalog CSV from GitHub and import into DB.

    Regions: AR_DUBAI, DE_BERLIN, ENG_TORONTO, SP_BARCELONA, FR_PARIS,
             HI_MUMBAI, PT_SAOPAULO, RU_STPETERSBURG, UK_GBP, USA_USD, ZH_SHANGHAI
    """
    import csv
    import io
    import urllib.request

    folder = REGION_MAP.get(region)
    if folder is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown region '{region}'. Valid regions: {', '.join(sorted(REGION_MAP))}",
        )

    # Belt-and-braces: `folder` and `region` come from the static REGION_MAP
    # only (already validated above), but URL-quote them anyway and verify the
    # final URL still has the trusted host. This makes the trust boundary
    # explicit and silences CodeQL's `py/partial-ssrf` finding.
    from urllib.parse import quote, urlparse
    url = f"{_GITHUB_BASE}/{quote(folder, safe='')}/DDC_CWICR_{quote(region, safe='')}_Catalog.csv"
    if urlparse(url).netloc != "raw.githubusercontent.com":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Catalog source host is not allowed.",
        )
    logger.info("Downloading catalog CSV: %s", url)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "OpenConstructionERP "
                    "(+https://datadrivenconstruction.io; DDC-CWICR-OE-2026)"
                )
            },
        )

        # Offload blocking urllib to a worker thread so the event loop
        # stays responsive during the 60-second download window.
        def _fetch() -> bytes:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — host pinned above
                return resp.read()

        raw_bytes = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.error("Failed to download catalog CSV from %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to download catalog from GitHub: {exc}",
        ) from exc

    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    from sqlalchemy import delete as sql_delete

    from app.modules.catalog.models import CatalogResource

    # Delete existing resources for this region (clean reimport)
    await session.execute(sql_delete(CatalogResource).where(CatalogResource.region == region))
    await session.flush()

    imported = 0
    skipped = 0

    _MAPPED_FIELDS = {
        "resource_code",
        "name",
        "type",
        "category",
        "unit",
        "price_avg",
        "price_min",
        "price_max",
        "currency",
        "usage_count",
    }

    batch: list[CatalogResource] = []
    BATCH_SIZE = 500

    for row in reader:
        resource_code = (row.get("resource_code") or "").strip()
        if not resource_code:
            skipped += 1
            continue

        # Build specifications from unmapped fields
        specifications: dict[str, Any] = {}
        for key, val in row.items():
            if key and key not in _MAPPED_FIELDS and val:
                specifications[key] = val

        try:
            resource = CatalogResource(
                resource_code=resource_code,
                name=(row.get("name") or resource_code).strip()[:500],
                resource_type=(row.get("type") or "material").strip().lower(),
                category=(row.get("category") or "General").strip(),
                unit=(row.get("unit") or "unit").strip()[:20],
                base_price=str(round(float(row.get("price_avg") or 0), 2)),
                min_price=str(round(float(row.get("price_min") or 0), 2)),
                max_price=str(round(float(row.get("price_max") or 0), 2)),
                currency=(row.get("currency") or "").strip(),
                usage_count=int(float(row.get("usage_count") or 0)),
                source="github_import",
                region=region,
                specifications=specifications,
                metadata_={},
            )
            batch.append(resource)
            imported += 1
        except (ValueError, TypeError):
            skipped += 1
            continue

        if len(batch) >= BATCH_SIZE:
            session.add_all(batch)
            await session.flush()
            batch.clear()

    if batch:
        session.add_all(batch)
        await session.flush()

    logger.info(
        "Catalog import complete for %s: %d imported, %d skipped",
        region,
        imported,
        skipped,
    )

    return {"imported": imported, "skipped": skipped, "region": region}


# ── List loaded regions ──────────────────────────────────────────────────


@router.get("/regions/")
async def list_catalog_regions(
    session: SessionDep,
) -> list[dict[str, Any]]:
    """‌⁠‍List loaded catalog regions with resource counts."""
    from app.modules.catalog.repository import CatalogResourceRepository

    repo = CatalogResourceRepository(session)
    return await repo.stats_by_region()


# ── Delete region ────────────────────────────────────────────────────────


@router.delete("/region/{region}")
async def delete_catalog_region(
    region: str,
    session: SessionDep,
    _user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("catalog.delete")),
) -> dict[str, Any]:
    """Remove all resources for a specific region."""
    from app.modules.catalog.repository import CatalogResourceRepository

    repo = CatalogResourceRepository(session)
    deleted = await repo.delete_by_region(region)
    logger.info("Deleted %d catalog resources for region %s", deleted, region)
    return {"deleted": deleted, "region": region}


# ── Bulk Price Adjustment ─────────────────────────────────────────────────


@router.patch(
    "/adjust-prices/",
    dependencies=[Depends(RequirePermission("catalog.create"))],
)
async def adjust_prices(
    session: SessionDep,
    _user_id: CurrentUserId,
    factor: float = Query(
        ..., gt=0, le=10, description="Multiplication factor (e.g. 1.05 for +5%), must be 0 < f ≤ 10"
    ),
    resource_type: str | None = Query(default=None, description="Filter by type: material, labor, equipment"),
    category: str | None = Query(default=None, description="Filter by category"),
    region: str | None = Query(default=None, description="Filter by region"),
) -> dict:
    """Adjust prices by a factor for filtered resources.

    Use cases:
    - Inflation adjustment: factor=1.05 (+5%)
    - Regional coefficient: factor=1.12 (Munich vs Berlin)
    - Discount: factor=0.95 (-5%)
    """
    # Explicit validation — Query(gt=, le=) may not be enforced in all FastAPI versions
    if factor <= 0 or factor > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Factor must be between 0 (exclusive) and 10 (inclusive), got {factor}",
        )

    from sqlalchemy import func, select

    from app.modules.catalog.models import CatalogResource

    # Build filter conditions using SQLAlchemy (DB-agnostic)
    conditions = [CatalogResource.is_active.is_(True)]
    if resource_type:
        conditions.append(CatalogResource.resource_type == resource_type)
    if category:
        conditions.append(CatalogResource.category == category)
    if region:
        conditions.append(CatalogResource.region == region)

    # Count matching rows first
    count_stmt = select(func.count()).select_from(CatalogResource).where(*conditions)
    count = (await session.execute(count_stmt)).scalar_one()

    if count > 0:
        # Fetch and update in batches via ORM to stay DB-agnostic
        stmt = select(CatalogResource).where(*conditions)
        result = await session.execute(stmt)
        resources = list(result.scalars().all())

        for res in resources:
            try:
                res.base_price = str(round(float(res.base_price) * factor, 2))
                res.min_price = str(round(float(res.min_price) * factor, 2))
                res.max_price = str(round(float(res.max_price) * factor, 2))
            except (ValueError, TypeError):
                pass

        await session.flush()

    logger.info(
        "Adjusted %d resource prices by factor %.4f (type=%s, category=%s, region=%s)",
        count,
        factor,
        resource_type,
        category,
        region,
    )

    return {
        "adjusted": count,
        "factor": factor,
        "filters": {
            "resource_type": resource_type,
            "category": category,
            "region": region,
        },
    }


# ── Search / List ─────────────────────────────────────────────────────────


@router.get("/", response_model=CatalogSearchResponse)
async def search_catalog(
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CatalogResourceService = Depends(_get_service),
    q: str | None = Query(default=None, description="Text search on code and name"),
    resource_type: str | None = Query(default=None, description="Filter: material, equipment, labor, operator"),
    category: str | None = Query(default=None, description="Filter by category"),
    region: str | None = Query(default=None, description="Filter by region"),
    unit: str | None = Query(default=None, description="Filter by unit"),
    min_price: float | None = Query(default=None, ge=0, description="Min base price"),
    max_price: float | None = Query(default=None, ge=0, description="Max base price"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CatalogSearchResponse:
    """Search and list catalog resources with optional filters."""
    from app.modules.catalog.schemas import CatalogSearchQuery

    query = CatalogSearchQuery(
        q=q,
        resource_type=resource_type,
        category=category,
        region=region,
        unit=unit,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset,
    )
    items, total = await service.search_resources(query)
    return CatalogSearchResponse(
        items=[CatalogResourceResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Stats ─────────────────────────────────────────────────────────────────


@router.get("/stats/", response_model=CatalogStatsResponse)
async def catalog_stats(
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CatalogResourceService = Depends(_get_service),
) -> CatalogStatsResponse:
    """Get aggregated counts by type and category."""
    return await service.get_stats()


# ── Inverse lookup: positions that use a resource ─────────────────────────
# Declared BEFORE ``/{resource_id}`` so FastAPI's ordered path-matcher
# considers the longer pattern first — otherwise the bare resource-id
# route can shadow this one.


@router.get("/{resource_id}/used-by/")
async def list_cost_positions_using_resource(
    resource_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List the cost positions that reference this resource.

    The catalog resource is the *leaf* (one material / labour rate /
    equipment item). Cost positions are the *compositions* — each one
    carries a ``components[]`` array naming the resources it consumes.
    This endpoint walks that link in the resource→positions direction:
    given a resource id, return every cost position whose
    ``components[].code`` matches the resource's ``resource_code``.

    Result shape:

    ::

        {
          "resource_code": "...",
          "items": [
            {"id": "...", "code": "...", "description": "...",
             "unit": "...", "rate": "...", "currency": "...",
             "region": "...",
             "component": {"quantity": 1.0, "unit_rate": ..., "cost": ..., "type": "material"}}
          ],
          "total": 106,
          "limit": 50,
          "offset": 0,
        }

    Implementation: SQLAlchemy + DB-side JSON ``LIKE`` filter on the
    serialised ``components`` column. We post-filter in Python to extract
    the matched ``component`` dict (the row may carry many components).
    For SQLite/Postgres parity we don't use JSON-path operators here —
    the LIKE on a small per-row payload is fast enough for catalog UI.
    """
    from sqlalchemy import func, or_, select

    from app.modules.catalog.models import CatalogResource
    from app.modules.costs.models import CostItem

    resource = (await session.execute(
        select(CatalogResource).where(CatalogResource.id == resource_id)
    )).scalar_one_or_none()
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    code = resource.resource_code
    # JSON column stored as text — match the code as a quoted substring so
    # we don't false-positive on prefix collisions ("ME_X" matching "ME_XYZ").
    needle = f'"code": "{code}"'
    needle_alt = f'"code":"{code}"'  # compact JSON variant

    base_filter = or_(
        func.cast(CostItem.components, String).like(f"%{needle}%"),
        func.cast(CostItem.components, String).like(f"%{needle_alt}%"),
    )

    total = (await session.execute(
        select(func.count()).select_from(CostItem).where(base_filter)
    )).scalar_one()

    rows = (await session.execute(
        select(CostItem)
        .where(base_filter)
        .order_by(CostItem.code, CostItem.id)
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        matched_component: dict[str, Any] | None = None
        for c in row.components or []:
            if isinstance(c, dict) and c.get("code") == code:
                matched_component = c
                break
        items.append({
            "id": str(row.id),
            "code": row.code,
            "description": row.description,
            "unit": row.unit,
            "rate": row.rate,
            "currency": row.currency,
            "region": row.region,
            "component": matched_component,
        })

    return {
        "resource_code": code,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── Single resource ───────────────────────────────────────────────────────


@router.get("/{resource_id}", response_model=CatalogResourceResponse)
async def get_catalog_resource(
    resource_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CatalogResourceService = Depends(_get_service),
) -> CatalogResourceResponse:
    """Get a single catalog resource by ID."""
    resource = await service.get_resource(resource_id)
    return CatalogResourceResponse.model_validate(resource)


# ── Create ────────────────────────────────────────────────────────────────


@router.post("/", response_model=CatalogResourceResponse, status_code=201)
async def create_catalog_resource(
    data: CatalogResourceCreate,
    service: CatalogResourceService = Depends(_get_service),
    _user: str = Depends(RequirePermission("catalog.create")),
) -> CatalogResourceResponse:
    """Create a new custom catalog resource."""
    resource = await service.create_resource(data)
    return CatalogResourceResponse.model_validate(resource)


# ── Extract from cost items ──────────────────────────────────────────────


@router.post("/extract/")
async def extract_resources(
    service: CatalogResourceService = Depends(_get_service),
    _user: str = Depends(RequirePermission("catalog.extract")),
) -> dict[str, Any]:
    """Extract top 100 resources from existing cost item components.

    This is an admin-level operation that:
    1. Scans all cost items for components
    2. Aggregates by component code and type
    3. Computes avg/min/max rates
    4. Categorizes resources
    5. Inserts top 100 (50 materials, 30 equipment, 10 labor, 10 operators)
    """
    counts = await service.extract_from_cost_items()
    total = sum(counts.values())
    return {
        "status": "success",
        "total_extracted": total,
        "by_type": counts,
    }
