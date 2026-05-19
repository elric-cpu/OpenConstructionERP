"""‌⁠‍Property Development API routes.

All routes are RBAC-gated and mounted by the module loader at
``/api/v1/property-dev/`` (slash inferred from module name).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.dependencies import RequirePermission, SessionDep
from app.modules.property_dev.schemas import (
    BuyerCancelRequest,
    BuyerConfiguratorResponse,
    BuyerContractRequest,
    BuyerCreate,
    BuyerOptionCreate,
    BuyerOptionGroupCreate,
    BuyerOptionGroupResponse,
    BuyerOptionGroupUpdate,
    BuyerOptionResponse,
    BuyerOptionUpdate,
    BuyerResponse,
    BuyerSelectionCreate,
    BuyerSelectionItemCreate,
    BuyerSelectionItemResponse,
    BuyerSelectionResponse,
    BuyerSelectionUpdate,
    BuyerUpdate,
    DepositForfeitureResponse,
    DevelopmentCreate,
    DevelopmentDashboard,
    DevelopmentPnLResponse,
    DevelopmentResponse,
    DevelopmentUpdate,
    HandoverBundleResponse,
    HandoverCompleteRequest,
    HandoverCreate,
    HandoverDocCreate,
    HandoverDocResponse,
    HandoverDocUpdate,
    HandoverResponse,
    HandoverUpdate,
    HouseTypeCreate,
    HouseTypeResponse,
    HouseTypeUpdate,
    HouseTypeVariantCreate,
    HouseTypeVariantResponse,
    HouseTypeVariantUpdate,
    PlotCreate,
    PlotPricingResponse,
    PlotReserveRequest,
    PlotResponse,
    PlotUpdate,
    ReservationCalendarResponse,
    SalesKanbanResponse,
    SnagCreate,
    SnagResponse,
    SnagUpdate,
    WarrantyClaimCreate,
    WarrantyClaimResponse,
    WarrantyClaimUpdate,
)
from app.modules.property_dev.service import (
    PropertyDevService,
    compute_plot_final_price,
    supported_jurisdictions,
)

router = APIRouter()


def _svc(session: SessionDep) -> PropertyDevService:
    return PropertyDevService(session)


# ── Developments ────────────────────────────────────────────────────────


@router.get("/developments/", response_model=list[DevelopmentResponse])
async def list_developments(
    service: PropertyDevService = Depends(_svc),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[DevelopmentResponse]:
    rows, _ = await service.developments.list_all(offset=offset, limit=limit)
    return [DevelopmentResponse.model_validate(r) for r in rows]


@router.post("/developments/", response_model=DevelopmentResponse, status_code=201)
async def create_development(
    data: DevelopmentCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> DevelopmentResponse:
    obj = await service.create_development(data)
    return DevelopmentResponse.model_validate(obj)


@router.get("/developments/{dev_id}", response_model=DevelopmentResponse)
async def get_development(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentResponse:
    obj = await service.get_development(dev_id)
    return DevelopmentResponse.model_validate(obj)


@router.patch("/developments/{dev_id}", response_model=DevelopmentResponse)
async def update_development(
    dev_id: uuid.UUID,
    data: DevelopmentUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> DevelopmentResponse:
    obj = await service.update_development(dev_id, data)
    return DevelopmentResponse.model_validate(obj)


@router.delete("/developments/{dev_id}", status_code=204)
async def delete_development(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_development(dev_id)


@router.get(
    "/developments/{dev_id}/dashboard",
    response_model=DevelopmentDashboard,
)
async def development_dashboard(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentDashboard:
    payload = await service.development_sales_dashboard(dev_id)
    return DevelopmentDashboard.model_validate(payload)


@router.get(
    "/developments/{dev_id}/sales-dashboard",
    response_model=DevelopmentDashboard,
)
async def development_sales_dashboard(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentDashboard:
    payload = await service.development_sales_dashboard(dev_id)
    return DevelopmentDashboard.model_validate(payload)


# ── Plots ───────────────────────────────────────────────────────────────


@router.get("/plots/", response_model=list[PlotResponse])
async def list_plots(
    development_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PlotResponse]:
    rows, _ = await service.plots.list_for_development(
        development_id, offset=offset, limit=limit, status=status
    )
    return [PlotResponse.model_validate(r) for r in rows]


@router.post("/plots/", response_model=PlotResponse, status_code=201)
async def create_plot(
    data: PlotCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PlotResponse:
    obj = await service.create_plot(data)
    return PlotResponse.model_validate(obj)


@router.get("/plots/{plot_id}", response_model=PlotResponse)
async def get_plot(
    plot_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PlotResponse:
    obj = await service.get_plot(plot_id)
    return PlotResponse.model_validate(obj)


@router.patch("/plots/{plot_id}", response_model=PlotResponse)
async def update_plot(
    plot_id: uuid.UUID,
    data: PlotUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PlotResponse:
    obj = await service.update_plot(plot_id, data)
    return PlotResponse.model_validate(obj)


@router.delete("/plots/{plot_id}", status_code=204)
async def delete_plot(
    plot_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_plot(plot_id)


@router.post("/plots/{plot_id}/reserve", response_model=PlotResponse)
async def reserve_plot(
    plot_id: uuid.UUID,
    data: PlotReserveRequest,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reserve_plot")),
) -> PlotResponse:
    plot, _ = await service.reserve_plot(plot_id, data)
    return PlotResponse.model_validate(plot)


@router.get(
    "/plots/{plot_id}/configurator",
    response_model=BuyerConfiguratorResponse,
)
async def plot_configurator(
    plot_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerConfiguratorResponse:
    plot = await service.get_plot(plot_id)
    house_type = (
        await service.house_types.get_by_id(plot.house_type_id)
        if plot.house_type_id
        else None
    )
    variant = (
        await service.variants.get_by_id(plot.house_type_variant_id)
        if plot.house_type_variant_id
        else None
    )

    groups = await service.option_groups.list_for_development(plot.development_id)
    options_by_group: dict[str, list[BuyerOptionResponse]] = {}
    for g in groups:
        opts = await service.options.list_active_options_for_group(g.id)
        options_by_group[str(g.id)] = [
            BuyerOptionResponse.model_validate(o) for o in opts
        ]

    buyer = await service.buyers.get_for_plot(plot_id)
    current_selection: Any = None
    current_items: list[Any] = []
    if buyer is not None:
        current_selection = await service.selections.current_selection_for_buyer(
            buyer.id
        )
        if current_selection is not None:
            current_items = await service.selection_items.list_for_selection(
                current_selection.id
            )

    pricing_total = compute_plot_final_price(plot, variant, current_items)
    pricing = PlotPricingResponse(
        plot_id=plot.id,
        base_price=Decimal(str(plot.price_base)),
        variant_modifier_value=(
            (Decimal(str(plot.price_base)) * Decimal(str(variant.modifier_pct))
             / Decimal("100"))
            if variant else Decimal("0")
        ),
        selections_total=sum(
            (Decimal(str(i.total_price)) for i in current_items), Decimal("0")
        ),
        final_price=pricing_total,
        currency=plot.currency or "",
    )

    return BuyerConfiguratorResponse(
        plot=PlotResponse.model_validate(plot),
        house_type=HouseTypeResponse.model_validate(house_type) if house_type else None,
        variant=HouseTypeVariantResponse.model_validate(variant) if variant else None,
        option_groups=[BuyerOptionGroupResponse.model_validate(g) for g in groups],
        options_by_group=options_by_group,
        current_selection=(
            BuyerSelectionResponse.model_validate(current_selection)
            if current_selection else None
        ),
        current_items=[
            BuyerSelectionItemResponse.model_validate(i) for i in current_items
        ],
        pricing=pricing,
    )


# ── House Types & Variants ──────────────────────────────────────────────


@router.get("/house-types/", response_model=list[HouseTypeResponse])
async def list_house_types(
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HouseTypeResponse]:
    rows = await service.house_types.list_for_development(development_id)
    return [HouseTypeResponse.model_validate(r) for r in rows]


@router.post(
    "/house-types/", response_model=HouseTypeResponse, status_code=201,
)
async def create_house_type(
    data: HouseTypeCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> HouseTypeResponse:
    obj = await service.create_house_type(data)
    return HouseTypeResponse.model_validate(obj)


@router.get("/house-types/{ht_id}", response_model=HouseTypeResponse)
async def get_house_type(
    ht_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HouseTypeResponse:
    return HouseTypeResponse.model_validate(await service.get_house_type(ht_id))


@router.patch("/house-types/{ht_id}", response_model=HouseTypeResponse)
async def update_house_type(
    ht_id: uuid.UUID,
    data: HouseTypeUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> HouseTypeResponse:
    obj = await service.update_house_type(ht_id, data)
    return HouseTypeResponse.model_validate(obj)


@router.delete("/house-types/{ht_id}", status_code=204)
async def delete_house_type(
    ht_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_house_type(ht_id)


@router.get(
    "/house-type-variants/", response_model=list[HouseTypeVariantResponse],
)
async def list_variants(
    house_type_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HouseTypeVariantResponse]:
    rows = await service.variants.list_for_house_type(house_type_id)
    return [HouseTypeVariantResponse.model_validate(r) for r in rows]


@router.post(
    "/house-type-variants/",
    response_model=HouseTypeVariantResponse,
    status_code=201,
)
async def create_variant(
    data: HouseTypeVariantCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> HouseTypeVariantResponse:
    return HouseTypeVariantResponse.model_validate(
        await service.create_variant(data)
    )


@router.get(
    "/house-type-variants/{v_id}", response_model=HouseTypeVariantResponse,
)
async def get_variant(
    v_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HouseTypeVariantResponse:
    return HouseTypeVariantResponse.model_validate(await service.get_variant(v_id))


@router.patch(
    "/house-type-variants/{v_id}", response_model=HouseTypeVariantResponse,
)
async def update_variant(
    v_id: uuid.UUID,
    data: HouseTypeVariantUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> HouseTypeVariantResponse:
    return HouseTypeVariantResponse.model_validate(
        await service.update_variant(v_id, data)
    )


@router.delete("/house-type-variants/{v_id}", status_code=204)
async def delete_variant(
    v_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_variant(v_id)


# ── Option Groups ───────────────────────────────────────────────────────


@router.get("/option-groups/", response_model=list[BuyerOptionGroupResponse])
async def list_option_groups(
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerOptionGroupResponse]:
    rows = await service.option_groups.list_for_development(development_id)
    return [BuyerOptionGroupResponse.model_validate(r) for r in rows]


@router.post(
    "/option-groups/", response_model=BuyerOptionGroupResponse, status_code=201,
)
async def create_option_group(
    data: BuyerOptionGroupCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerOptionGroupResponse:
    return BuyerOptionGroupResponse.model_validate(
        await service.create_option_group(data)
    )


@router.get("/option-groups/{g_id}", response_model=BuyerOptionGroupResponse)
async def get_option_group(
    g_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerOptionGroupResponse:
    return BuyerOptionGroupResponse.model_validate(
        await service.get_option_group(g_id)
    )


@router.patch("/option-groups/{g_id}", response_model=BuyerOptionGroupResponse)
async def update_option_group(
    g_id: uuid.UUID,
    data: BuyerOptionGroupUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerOptionGroupResponse:
    return BuyerOptionGroupResponse.model_validate(
        await service.update_option_group(g_id, data)
    )


@router.delete("/option-groups/{g_id}", status_code=204)
async def delete_option_group(
    g_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_option_group(g_id)


# ── Options ─────────────────────────────────────────────────────────────


@router.get("/options/", response_model=list[BuyerOptionResponse])
async def list_options(
    group_id: uuid.UUID = Query(...),
    active_only: bool = Query(default=True),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerOptionResponse]:
    rows = await service.options.list_for_group(group_id, active_only=active_only)
    return [BuyerOptionResponse.model_validate(r) for r in rows]


@router.post("/options/", response_model=BuyerOptionResponse, status_code=201)
async def create_option(
    data: BuyerOptionCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerOptionResponse:
    return BuyerOptionResponse.model_validate(await service.create_option(data))


@router.get("/options/{o_id}", response_model=BuyerOptionResponse)
async def get_option(
    o_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerOptionResponse:
    return BuyerOptionResponse.model_validate(await service.get_option(o_id))


@router.patch("/options/{o_id}", response_model=BuyerOptionResponse)
async def update_option(
    o_id: uuid.UUID,
    data: BuyerOptionUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerOptionResponse:
    return BuyerOptionResponse.model_validate(
        await service.update_option(o_id, data)
    )


@router.delete("/options/{o_id}", status_code=204)
async def delete_option(
    o_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_option(o_id)


# ── Buyers ──────────────────────────────────────────────────────────────


@router.get("/buyers/", response_model=list[BuyerResponse])
async def list_buyers(
    development_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerResponse]:
    rows, _ = await service.buyers.list_for_development(
        development_id, offset=offset, limit=limit, status=status
    )
    return [BuyerResponse.model_validate(r) for r in rows]


@router.post("/buyers/", response_model=BuyerResponse, status_code=201)
async def create_buyer(
    data: BuyerCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerResponse:
    return BuyerResponse.model_validate(await service.create_buyer(data))


@router.get("/buyers/{b_id}", response_model=BuyerResponse)
async def get_buyer(
    b_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerResponse:
    return BuyerResponse.model_validate(await service.get_buyer(b_id))


@router.patch("/buyers/{b_id}", response_model=BuyerResponse)
async def update_buyer(
    b_id: uuid.UUID,
    data: BuyerUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerResponse:
    return BuyerResponse.model_validate(await service.update_buyer(b_id, data))


@router.delete("/buyers/{b_id}", status_code=204)
async def delete_buyer(
    b_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_buyer(b_id)


@router.post("/buyers/{b_id}/contract", response_model=BuyerResponse)
async def contract_buyer(
    b_id: uuid.UUID,
    data: BuyerContractRequest,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.contract_buyer")),
) -> BuyerResponse:
    return BuyerResponse.model_validate(
        await service.convert_buyer_to_contracted(b_id, data)
    )


# ── Selections ──────────────────────────────────────────────────────────


@router.get("/selections/", response_model=list[BuyerSelectionResponse])
async def list_selections(
    buyer_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerSelectionResponse]:
    rows = await service.selections.list_for_buyer(buyer_id)
    return [BuyerSelectionResponse.model_validate(r) for r in rows]


@router.post(
    "/selections/", response_model=BuyerSelectionResponse, status_code=201,
)
async def create_selection(
    data: BuyerSelectionCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerSelectionResponse:
    return BuyerSelectionResponse.model_validate(
        await service.create_selection(data)
    )


@router.get("/selections/{s_id}", response_model=BuyerSelectionResponse)
async def get_selection(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerSelectionResponse:
    return BuyerSelectionResponse.model_validate(await service.get_selection(s_id))


@router.patch("/selections/{s_id}", response_model=BuyerSelectionResponse)
async def update_selection(
    s_id: uuid.UUID,
    data: BuyerSelectionUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionResponse:
    return BuyerSelectionResponse.model_validate(
        await service.update_selection(s_id, data)
    )


@router.delete("/selections/{s_id}", status_code=204)
async def delete_selection(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_selection(s_id)


@router.post(
    "/selections/{s_id}/submit", response_model=BuyerSelectionResponse,
)
async def submit_selection(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionResponse:
    return BuyerSelectionResponse.model_validate(
        await service.submit_selection(s_id)
    )


@router.post(
    "/selections/{s_id}/lock", response_model=BuyerSelectionResponse,
)
async def lock_selection(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lock_selection")),
) -> BuyerSelectionResponse:
    return BuyerSelectionResponse.model_validate(
        await service.lock_selection(s_id)
    )


@router.post(
    "/selections/{s_id}/items",
    response_model=BuyerSelectionItemResponse,
    status_code=201,
)
async def add_selection_item(
    s_id: uuid.UUID,
    data: BuyerSelectionItemCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionItemResponse:
    return BuyerSelectionItemResponse.model_validate(
        await service.add_selection_item(s_id, data)
    )


@router.delete(
    "/selections/{s_id}/items/{item_id}", status_code=204,
)
async def remove_selection_item(
    s_id: uuid.UUID,
    item_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> None:
    # ``s_id`` kept for URL clarity; we look up via item itself.
    _ = s_id
    await service.remove_selection_item(item_id)


@router.post(
    "/selections/{s_id}/submit-for-production",
    response_model=BuyerSelectionResponse,
)
async def selection_submit_for_production(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lock_selection")),
) -> BuyerSelectionResponse:
    sel = await service.get_selection(s_id)
    result = await service.submit_for_production(sel.buyer_id)
    return BuyerSelectionResponse.model_validate(result)


# ── Handovers ───────────────────────────────────────────────────────────


@router.get("/handovers/", response_model=list[HandoverResponse])
async def list_handovers(
    plot_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HandoverResponse]:
    rows = await service.handovers.list_for_plot(plot_id)
    return [HandoverResponse.model_validate(r) for r in rows]


@router.post("/handovers/", response_model=HandoverResponse, status_code=201)
async def create_handover(
    data: HandoverCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    return HandoverResponse.model_validate(await service.create_handover(data))


@router.get("/handovers/{h_id}", response_model=HandoverResponse)
async def get_handover(
    h_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HandoverResponse:
    return HandoverResponse.model_validate(await service.get_handover(h_id))


@router.patch("/handovers/{h_id}", response_model=HandoverResponse)
async def update_handover(
    h_id: uuid.UUID,
    data: HandoverUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    return HandoverResponse.model_validate(
        await service.update_handover(h_id, data)
    )


@router.delete("/handovers/{h_id}", status_code=204)
async def delete_handover(
    h_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_handover(h_id)


@router.post("/handovers/{h_id}/complete", response_model=HandoverResponse)
async def complete_handover(
    h_id: uuid.UUID,
    data: HandoverCompleteRequest,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    return HandoverResponse.model_validate(
        await service.complete_handover(h_id, data)
    )


# ── Snags ───────────────────────────────────────────────────────────────


@router.get("/snags/", response_model=list[SnagResponse])
async def list_snags(
    handover_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[SnagResponse]:
    rows = await service.snags.list_for_handover(handover_id, status=status)
    return [SnagResponse.model_validate(r) for r in rows]


@router.post("/snags/", response_model=SnagResponse, status_code=201)
async def create_snag(
    data: SnagCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> SnagResponse:
    return SnagResponse.model_validate(await service.create_snag(data))


@router.get("/snags/{s_id}", response_model=SnagResponse)
async def get_snag(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> SnagResponse:
    return SnagResponse.model_validate(await service.get_snag(s_id))


@router.patch("/snags/{s_id}", response_model=SnagResponse)
async def update_snag(
    s_id: uuid.UUID,
    data: SnagUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    return SnagResponse.model_validate(await service.update_snag(s_id, data))


@router.delete("/snags/{s_id}", status_code=204)
async def delete_snag(
    s_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_snag(s_id)


@router.post("/snags/{s_id}/fix", response_model=SnagResponse)
async def fix_snag(
    s_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    fix_notes = (payload or {}).get("fix_notes")
    return SnagResponse.model_validate(
        await service.mark_snag_fixed(s_id, fix_notes=fix_notes)
    )


@router.post("/snags/{s_id}/wont-fix", response_model=SnagResponse)
async def wont_fix_snag(
    s_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    fix_notes = (payload or {}).get("fix_notes")
    return SnagResponse.model_validate(
        await service.mark_snag_wont_fix(s_id, fix_notes=fix_notes)
    )


# ── Warranty Claims ─────────────────────────────────────────────────────


@router.get("/warranty-claims/", response_model=list[WarrantyClaimResponse])
async def list_warranty_claims(
    buyer_id: uuid.UUID | None = Query(default=None),
    plot_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[WarrantyClaimResponse]:
    if buyer_id is not None:
        rows = await service.warranty.list_for_buyer(buyer_id, status=status)
    elif plot_id is not None:
        rows = await service.warranty.list_for_plot(plot_id, status=status)
    else:
        rows = []
    return [WarrantyClaimResponse.model_validate(r) for r in rows]


@router.post(
    "/warranty-claims/", response_model=WarrantyClaimResponse, status_code=201,
)
async def create_warranty_claim(
    data: WarrantyClaimCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(
        await service.raise_warranty_claim(data.plot_id, data.buyer_id, data)
    )


@router.get(
    "/warranty-claims/{w_id}", response_model=WarrantyClaimResponse,
)
async def get_warranty_claim(
    w_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(await service.get_warranty(w_id))


@router.patch(
    "/warranty-claims/{w_id}", response_model=WarrantyClaimResponse,
)
async def update_warranty_claim(
    w_id: uuid.UUID,
    data: WarrantyClaimUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(
        await service.update_warranty(w_id, data)
    )


@router.delete("/warranty-claims/{w_id}", status_code=204)
async def delete_warranty_claim(
    w_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_warranty(w_id)


@router.post(
    "/warranty/{w_id}/accept", response_model=WarrantyClaimResponse,
)
async def accept_warranty_claim(
    w_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(await service.warranty_accept(w_id))


@router.post(
    "/warranty/{w_id}/reject", response_model=WarrantyClaimResponse,
)
async def reject_warranty_claim(
    w_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(await service.warranty_reject(w_id))


@router.post(
    "/warranty/{w_id}/close", response_model=WarrantyClaimResponse,
)
async def close_warranty_claim(
    w_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    return WarrantyClaimResponse.model_validate(await service.warranty_close(w_id))


# ── Cancel buyer + deposit forfeiture ──────────────────────────────────


@router.post("/buyers/{b_id}/cancel", response_model=DepositForfeitureResponse)
async def cancel_buyer(
    b_id: uuid.UUID,
    data: BuyerCancelRequest,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> DepositForfeitureResponse:
    """‌⁠‍Cancel a buyer + compute jurisdiction-specific deposit forfeiture."""
    _buyer, forfeiture = await service.cancel_buyer(b_id, data)
    return DepositForfeitureResponse(
        buyer_id=b_id,
        jurisdiction=forfeiture["jurisdiction"],
        deposit_amount=forfeiture["deposit_amount"],
        forfeited_amount=forfeiture["forfeited_amount"],
        refundable_amount=forfeiture["refundable_amount"],
        rule_citation=forfeiture["rule_citation"],
        rule_summary=forfeiture["rule_summary"],
    )


@router.get("/jurisdictions", response_model=list[str])
async def list_jurisdictions(
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[str]:
    """‌⁠‍List ISO-3166 alpha-2 codes with a real deposit-forfeiture rule."""
    return supported_jurisdictions()


# ── Handover doc bundle (buyer-portal hand-off) ────────────────────────


@router.get(
    "/handovers/{h_id}/docs", response_model=HandoverBundleResponse,
)
async def get_handover_bundle(
    h_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HandoverBundleResponse:
    """Return the full handover-doc bundle with compliance status."""
    payload = await service.handover_bundle(h_id)
    return HandoverBundleResponse(
        handover_id=payload["handover_id"],
        docs=[HandoverDocResponse.model_validate(d) for d in payload["docs"]],
        delivered_count=payload["delivered_count"],
        required_count=payload["required_count"],
        missing_required=payload["missing_required"],
        ready_for_handover=payload["ready_for_handover"],
    )


@router.post(
    "/handover-docs/",
    response_model=HandoverDocResponse,
    status_code=201,
)
async def create_handover_doc(
    data: HandoverDocCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverDocResponse:
    return HandoverDocResponse.model_validate(
        await service.create_handover_doc(data)
    )


@router.patch(
    "/handover-docs/{doc_id}", response_model=HandoverDocResponse,
)
async def update_handover_doc(
    doc_id: uuid.UUID,
    data: HandoverDocUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverDocResponse:
    return HandoverDocResponse.model_validate(
        await service.update_handover_doc(doc_id, data)
    )


@router.delete("/handover-docs/{doc_id}", status_code=204)
async def delete_handover_doc(
    doc_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_handover_doc(doc_id)


# ── Sales pipeline + reservation calendar + dev P&L ────────────────────


@router.get(
    "/developments/{dev_id}/sales-kanban",
    response_model=SalesKanbanResponse,
)
async def sales_kanban(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> SalesKanbanResponse:
    """Kanban — one column per buyer-status."""
    payload = await service.sales_kanban(dev_id)
    return SalesKanbanResponse(**payload)


@router.get(
    "/developments/{dev_id}/reservation-calendar",
    response_model=ReservationCalendarResponse,
)
async def reservation_calendar(
    dev_id: uuid.UUID,
    period_start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    period_end: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> ReservationCalendarResponse:
    """Reservation + freeze + contract deadlines in the supplied window."""
    payload = await service.reservation_calendar(
        dev_id, period_start, period_end,
    )
    return ReservationCalendarResponse(**payload)


@router.get(
    "/developments/{dev_id}/pnl",
    response_model=DevelopmentPnLResponse,
)
async def development_pnl(
    dev_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentPnLResponse:
    """Revenue + deposits + open-issues rollup for a development."""
    payload = await service.development_pnl(dev_id)
    return DevelopmentPnLResponse(**payload)
