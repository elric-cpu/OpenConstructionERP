"""‌⁠‍Property Development API routes.

All routes are RBAC-gated and mounted by the module loader at
``/api/v1/property-dev/`` (slash inferred from module name).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import CurrentUserPayload, RequirePermission, SessionDep
from app.modules.property_dev.schemas import (
    BlockCreate,
    BlockResponse,
    BlockUpdate,
    BrokerCreate,
    BrokerResponse,
    BrokerUpdate,
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
    CommissionAccrualPayRequest,
    CommissionAccrualResponse,
    CommissionAgreementCreate,
    CommissionAgreementResponse,
    CommissionAgreementUpdate,
    ContractPartyCreate,
    ContractPartyResponse,
    ContractPartyUpdate,
    ContractTaxQuote,
    DepositForfeitureResponse,
    DevelopmentCreate,
    DevelopmentDashboard,
    DevelopmentPnLResponse,
    DevelopmentResponse,
    DevelopmentUpdate,
    EscrowAccountCreate,
    EscrowAccountResponse,
    EscrowAccountUpdate,
    EscrowBalanceResponse,
    EscrowTransactionCreate,
    EscrowTransactionReconcileRequest,
    EscrowTransactionResponse,
    EscrowTransactionUpdate,
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
    InstalmentCreate,
    InstalmentMarkPaidRequest,
    InstalmentResponse,
    InstalmentUpdate,
    InstalmentWaiveRequest,
    LeadConvertToReservationRequest,
    LeadCreate,
    LeadResponse,
    LeadUpdate,
    PaymentScheduleCreate,
    PaymentScheduleResponse,
    PaymentScheduleUpdate,
    PhaseCreate,
    PhaseResponse,
    PhaseUpdate,
    PlotCreate,
    PlotPricingResponse,
    PlotReserveRequest,
    PlotResponse,
    PlotUpdate,
    PriceMatrixBulkRecomputeResponse,
    PriceMatrixCreate,
    PriceMatrixPreviewResponse,
    PriceMatrixResponse,
    PriceMatrixUpdate,
    RegulatorReportResponse,
    ReservationCalendarResponse,
    ReservationConvertToSpaRequest,
    ReservationCreate,
    ReservationExpiryBatchResponse,
    ReservationResponse,
    ReservationUpdate,
    SalesContractCreate,
    SalesContractResponse,
    SalesContractSendForSignatureRequest,
    SalesContractSignRequest,
    SalesContractUpdate,
    SalesKanbanResponse,
    SnagCreate,
    SnagResponse,
    SnagUpdate,
    TaxQuotePayload,
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


async def _verify_buyer_owner(
    session: SessionDep,
    buyer_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """Confirm the calling user owns the project behind this buyer.

    Closes a cross-tenant write IDOR on ``PATCH /buyers/{b_id}``: without
    this guard, any user with ``property_dev.update`` could mutate any
    other tenant's buyer just by guessing UUIDs. Admins bypass.

    Resolves the chain buyer → development → project.owner_id and either
    raises 404 (when the buyer does not exist OR is owned by a different
    user, so we never leak existence) or returns silently.
    """
    is_admin = payload.get("role") == "admin"
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        # Should not happen — RequirePermission already ensures auth —
        # but be conservative and 401-style 404 the request.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found"
        )

    from app.modules.projects.repository import ProjectRepository
    from app.modules.property_dev.repository import (
        BuyerRepository,
        DevelopmentRepository,
    )

    buyer = await BuyerRepository(session).get_by_id(buyer_id)
    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found"
        )
    if is_admin:
        return

    development = await DevelopmentRepository(session).get_by_id(
        buyer.development_id,
    )
    if development is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found"
        )
    project = await ProjectRepository(session).get_by_id(development.project_id)
    if project is None or str(project.owner_id) != str(user_id):
        # 404 (not 403) — collapse "exists but not yours" into the same
        # response as "doesn't exist" so this endpoint can't be turned
        # into a UUID-existence oracle for other tenants' buyers.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found"
        )


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
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerResponse:
    # Cross-tenant write IDOR gate (task #134). Verifies the buyer's
    # development belongs to a project owned by the caller, or that the
    # caller is admin. Bumps 404 (not 403) on cross-tenant access to
    # avoid leaking existence of other tenants' buyer UUIDs.
    await _verify_buyer_owner(session, b_id, payload)
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



# ════════════════════════════════════════════════════════════════════════
# R6 — Lead / Reservation / SPA / PaymentSchedule / Instalment /
#       ContractParty
# ════════════════════════════════════════════════════════════════════════


async def _verify_owner_via_plot(
    session: SessionDep,
    plot_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """Generic IDOR closure walking plot → development → project owner.

    Collapses "exists but not yours" to 404 to avoid leaking UUID
    existence. Admins bypass.
    """
    is_admin = payload.get("role") == "admin"
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    from app.modules.projects.repository import ProjectRepository
    from app.modules.property_dev.repository import (
        DevelopmentRepository,
        PlotRepository,
    )

    plot = await PlotRepository(session).get_by_id(plot_id)
    if plot is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if is_admin:
        return
    dev = await DevelopmentRepository(session).get_by_id(plot.development_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    project = await ProjectRepository(session).get_by_id(dev.project_id)
    if project is None or str(project.owner_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Resource not found")


async def _verify_owner_via_development(
    session: SessionDep,
    dev_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure walking development → project owner."""
    is_admin = payload.get("role") == "admin"
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    from app.modules.projects.repository import ProjectRepository
    from app.modules.property_dev.repository import DevelopmentRepository

    dev = await DevelopmentRepository(session).get_by_id(dev_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if is_admin:
        return
    project = await ProjectRepository(session).get_by_id(dev.project_id)
    if project is None or str(project.owner_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Resource not found")


async def _verify_owner_via_lead(
    session: SessionDep,
    lead_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Lead (lead → development → project owner).

    Leads without a development_id are owner-less by design (top-of-funnel
    inbound webhooks); they are accessible by any authenticated user with
    the right permission level but never escape into another tenant since
    they carry no project-scoped data.
    """
    is_admin = payload.get("role") == "admin"
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    from app.modules.property_dev.repository import LeadRepository

    lead = await LeadRepository(session).get_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if is_admin or lead.development_id is None:
        return
    await _verify_owner_via_development(session, lead.development_id, payload)


async def _verify_owner_via_reservation(
    session: SessionDep,
    r_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    from app.modules.property_dev.repository import ReservationRepository

    res = await ReservationRepository(session).get_by_id(r_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_plot(session, res.plot_id, payload)


async def _verify_owner_via_spa(
    session: SessionDep,
    spa_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    from app.modules.property_dev.repository import SalesContractRepository

    spa = await SalesContractRepository(session).get_by_id(spa_id)
    if spa is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_plot(session, spa.plot_id, payload)


async def _verify_owner_via_schedule(
    session: SessionDep,
    schedule_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    from app.modules.property_dev.repository import PaymentScheduleRepository

    sched = await PaymentScheduleRepository(session).get_by_id(schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_spa(session, sched.sales_contract_id, payload)


async def _verify_owner_via_instalment(
    session: SessionDep,
    ins_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    from app.modules.property_dev.repository import InstalmentRepository

    ins = await InstalmentRepository(session).get_by_id(ins_id)
    if ins is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_schedule(session, ins.schedule_id, payload)


async def _verify_owner_via_party(
    session: SessionDep,
    party_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    from app.modules.property_dev.repository import ContractPartyRepository

    party = await ContractPartyRepository(session).get_by_id(party_id)
    if party is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_spa(session, party.sales_contract_id, payload)


# ── Leads ───────────────────────────────────────────────────────────────


@router.get("/leads/", response_model=list[LeadResponse])
async def list_leads(
    development_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    assigned_agent_user_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.read")),
) -> list[LeadResponse]:
    rows, _ = await service.leads.list_filtered(
        development_id=development_id,
        status=status,
        source=source,
        assigned_agent_user_id=assigned_agent_user_id,
        offset=offset,
        limit=limit,
    )
    return [LeadResponse.model_validate(r) for r in rows]


@router.post("/leads/", response_model=LeadResponse, status_code=201)
async def create_lead(
    data: LeadCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.create")),
) -> LeadResponse:
    return LeadResponse.model_validate(await service.create_lead(data))


@router.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.read")),
) -> LeadResponse:
    await _verify_owner_via_lead(session, lead_id, payload)
    return LeadResponse.model_validate(await service.get_lead(lead_id))


@router.patch("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    data: LeadUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.update")),
) -> LeadResponse:
    await _verify_owner_via_lead(session, lead_id, payload)
    return LeadResponse.model_validate(await service.update_lead(lead_id, data))


@router.delete("/leads/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.delete")),
) -> None:
    await _verify_owner_via_lead(session, lead_id, payload)
    await service.delete_lead(lead_id)


@router.post(
    "/leads/{lead_id}/convert-to-reservation",
    response_model=ReservationResponse,
    status_code=201,
)
async def convert_lead_to_reservation(
    lead_id: uuid.UUID,
    data: LeadConvertToReservationRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.convert")),
) -> ReservationResponse:
    await _verify_owner_via_lead(session, lead_id, payload)
    await _verify_owner_via_plot(session, data.plot_id, payload)
    return ReservationResponse.model_validate(
        await service.convert_lead_to_reservation(lead_id, data)
    )


# ── Reservations ────────────────────────────────────────────────────────


@router.get("/reservations/", response_model=list[ReservationResponse])
async def list_reservations(
    plot_id: uuid.UUID | None = Query(default=None),
    development_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.read")),
) -> list[ReservationResponse]:
    rows, _ = await service.reservations.list_filtered(
        plot_id=plot_id,
        development_id=development_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return [ReservationResponse.model_validate(r) for r in rows]


@router.post(
    "/reservations/", response_model=ReservationResponse, status_code=201,
)
async def create_reservation(
    data: ReservationCreate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.create")),
) -> ReservationResponse:
    await _verify_owner_via_plot(session, data.plot_id, payload)
    return ReservationResponse.model_validate(
        await service.create_reservation(data)
    )


@router.post(
    "/reservations/expire-overdue",
    response_model=ReservationExpiryBatchResponse,
)
async def expire_overdue_reservations(
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.expire")),
) -> ReservationExpiryBatchResponse:
    """Admin/cron endpoint — expire every active reservation past
    ``expires_at``. Idempotent + safe to schedule daily.
    """
    ids = await service.expire_overdue_reservations()
    return ReservationExpiryBatchResponse(
        expired_count=len(ids), expired_ids=ids
    )


@router.get("/reservations/{r_id}", response_model=ReservationResponse)
async def get_reservation(
    r_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.read")),
) -> ReservationResponse:
    await _verify_owner_via_reservation(session, r_id, payload)
    return ReservationResponse.model_validate(
        await service.get_reservation(r_id)
    )


@router.patch("/reservations/{r_id}", response_model=ReservationResponse)
async def update_reservation(
    r_id: uuid.UUID,
    data: ReservationUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.update")),
) -> ReservationResponse:
    await _verify_owner_via_reservation(session, r_id, payload)
    return ReservationResponse.model_validate(
        await service.update_reservation(r_id, data)
    )


@router.post(
    "/reservations/{r_id}/cancel", response_model=ReservationResponse,
)
async def cancel_reservation(
    r_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.cancel")),
) -> ReservationResponse:
    await _verify_owner_via_reservation(session, r_id, payload)
    return ReservationResponse.model_validate(
        await service.cancel_reservation(r_id)
    )


@router.post(
    "/reservations/{r_id}/expire", response_model=ReservationResponse,
)
async def expire_reservation(
    r_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reservation.expire")),
) -> ReservationResponse:
    await _verify_owner_via_reservation(session, r_id, payload)
    return ReservationResponse.model_validate(
        await service.expire_reservation(r_id)
    )


@router.post(
    "/reservations/{r_id}/convert-to-spa",
    response_model=SalesContractResponse,
    status_code=201,
)
async def convert_reservation_to_spa(
    r_id: uuid.UUID,
    data: ReservationConvertToSpaRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.draft")),
) -> SalesContractResponse:
    await _verify_owner_via_reservation(session, r_id, payload)
    return SalesContractResponse.model_validate(
        await service.convert_reservation_to_spa(r_id, data)
    )


# ── SalesContracts (SPAs) ───────────────────────────────────────────────


@router.get("/sales-contracts/", response_model=list[SalesContractResponse])
async def list_sales_contracts(
    session: SessionDep,
    payload: CurrentUserPayload,
    plot_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[SalesContractResponse]:
    await _verify_owner_via_plot(session, plot_id, payload)
    rows = await service.sales_contracts.list_for_plot(plot_id, status=status)
    return [SalesContractResponse.model_validate(r) for r in rows]


@router.post(
    "/sales-contracts/",
    response_model=SalesContractResponse,
    status_code=201,
)
async def create_sales_contract(
    data: SalesContractCreate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.draft")),
) -> SalesContractResponse:
    await _verify_owner_via_plot(session, data.plot_id, payload)
    return SalesContractResponse.model_validate(await service.create_spa(data))


@router.get(
    "/sales-contracts/{spa_id}", response_model=SalesContractResponse,
)
async def get_sales_contract(
    spa_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> SalesContractResponse:
    await _verify_owner_via_spa(session, spa_id, payload)
    return SalesContractResponse.model_validate(await service.get_spa(spa_id))


@router.patch(
    "/sales-contracts/{spa_id}", response_model=SalesContractResponse,
)
async def update_sales_contract(
    spa_id: uuid.UUID,
    data: SalesContractUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.draft")),
) -> SalesContractResponse:
    await _verify_owner_via_spa(session, spa_id, payload)
    return SalesContractResponse.model_validate(
        await service.update_spa(spa_id, data)
    )


@router.delete("/sales-contracts/{spa_id}", status_code=204)
async def delete_sales_contract(
    spa_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.cancel")),
) -> None:
    await _verify_owner_via_spa(session, spa_id, payload)
    await service.delete_spa(spa_id)


@router.post(
    "/sales-contracts/{spa_id}/send-for-signature",
    response_model=SalesContractResponse,
)
async def send_spa_for_signature(
    spa_id: uuid.UUID,
    data: SalesContractSendForSignatureRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.send")),
) -> SalesContractResponse:
    await _verify_owner_via_spa(session, spa_id, payload)
    return SalesContractResponse.model_validate(
        await service.send_spa_for_signature(spa_id, data)
    )


@router.post(
    "/sales-contracts/{spa_id}/sign", response_model=SalesContractResponse,
)
async def sign_sales_contract(
    spa_id: uuid.UUID,
    data: SalesContractSignRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.sign")),
) -> SalesContractResponse:
    await _verify_owner_via_spa(session, spa_id, payload)
    return SalesContractResponse.model_validate(
        await service.sign_spa(spa_id, data)
    )


@router.post(
    "/sales-contracts/{spa_id}/cancel", response_model=SalesContractResponse,
)
async def cancel_sales_contract(
    spa_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.spa.cancel")),
) -> SalesContractResponse:
    await _verify_owner_via_spa(session, spa_id, payload)
    return SalesContractResponse.model_validate(await service.cancel_spa(spa_id))


@router.post(
    "/sales-contracts/{spa_id}/tax-quote",
    response_model=ContractTaxQuote,
)
async def quote_sales_contract_taxes(
    spa_id: uuid.UUID,
    data: TaxQuotePayload,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> ContractTaxQuote:
    """Compute jurisdiction-aware taxes for a SalesContract.

    Routes UK SDLT progressive bands, DE state-specific Grunderwerbsteuer,
    UAE DLD transfer fee, IN GST + state stamp duty, SG BSD + ABSD,
    AU state stamp duty, US state transfer tax — all data-driven via
    ``data/tax_rates.yaml``. Returns Decimal amounts (2 dp HALF_UP)
    plus a human-readable breakdown for invoice rendering.
    """
    # IDOR — close cross-tenant read first (404 not 403 = no UUID oracle).
    await _verify_owner_via_spa(session, spa_id, payload)

    from app.modules.property_dev.tax_engine import (
        MissingRegionSubcodeError,
        UnknownRateClassError,
        UnsupportedJurisdictionError,
    )

    try:
        result = await service.quote_contract_taxes(
            spa_id,
            jurisdiction=data.jurisdiction,
            region_subcode=data.region_subcode,
            is_first_home=data.is_first_home,
            is_additional_property=data.is_additional_property,
            vat_rate_class=data.vat_rate_class,
            absd_buyer_profile=data.absd_buyer_profile,
            emirate=data.emirate,
            include_overdue=data.include_overdue,
        )
    except UnsupportedJurisdictionError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_jurisdiction",
                "jurisdiction": exc.jurisdiction,
                "supported": exc.supported,
                "message": str(exc),
            },
        )
    except MissingRegionSubcodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_region_subcode",
                "jurisdiction": exc.jurisdiction,
                "supported": exc.supported,
                "message": str(exc),
            },
        )
    except UnknownRateClassError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_rate_class",
                "message": str(exc),
            },
        )
    return ContractTaxQuote.model_validate(result)


# ── PaymentSchedules ────────────────────────────────────────────────────


@router.post(
    "/payment-schedules/",
    response_model=PaymentScheduleResponse,
    status_code=201,
)
async def create_payment_schedule(
    data: PaymentScheduleCreate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> PaymentScheduleResponse:
    await _verify_owner_via_spa(session, data.sales_contract_id, payload)
    return PaymentScheduleResponse.model_validate(
        await service.create_payment_schedule(data)
    )


@router.get(
    "/payment-schedules/{schedule_id}",
    response_model=PaymentScheduleResponse,
)
async def get_payment_schedule(
    schedule_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PaymentScheduleResponse:
    await _verify_owner_via_schedule(session, schedule_id, payload)
    return PaymentScheduleResponse.model_validate(
        await service.get_payment_schedule(schedule_id)
    )


@router.patch(
    "/payment-schedules/{schedule_id}",
    response_model=PaymentScheduleResponse,
)
async def update_payment_schedule(
    schedule_id: uuid.UUID,
    data: PaymentScheduleUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> PaymentScheduleResponse:
    await _verify_owner_via_schedule(session, schedule_id, payload)
    return PaymentScheduleResponse.model_validate(
        await service.update_payment_schedule(schedule_id, data)
    )


@router.post(
    "/payment-schedules/{schedule_id}/activate",
    response_model=PaymentScheduleResponse,
)
async def activate_payment_schedule(
    schedule_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> PaymentScheduleResponse:
    await _verify_owner_via_schedule(session, schedule_id, payload)
    return PaymentScheduleResponse.model_validate(
        await service.activate_payment_schedule(schedule_id)
    )


@router.post(
    "/payment-schedules/{schedule_id}/suspend",
    response_model=PaymentScheduleResponse,
)
async def suspend_payment_schedule(
    schedule_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.suspend")
    ),
) -> PaymentScheduleResponse:
    await _verify_owner_via_schedule(session, schedule_id, payload)
    return PaymentScheduleResponse.model_validate(
        await service.suspend_payment_schedule(schedule_id)
    )


# ── Instalments ─────────────────────────────────────────────────────────


@router.get("/instalments/", response_model=list[InstalmentResponse])
async def list_instalments(
    session: SessionDep,
    payload: CurrentUserPayload,
    schedule_id: uuid.UUID | None = Query(default=None),
    sales_contract_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[InstalmentResponse]:
    if schedule_id is not None:
        await _verify_owner_via_schedule(session, schedule_id, payload)
        rows = await service.instalments.list_for_schedule(
            schedule_id, status=status
        )
    elif sales_contract_id is not None:
        await _verify_owner_via_spa(session, sales_contract_id, payload)
        rows = await service.instalments.list_for_contract(sales_contract_id)
        if status:
            rows = [r for r in rows if r.status == status]
    else:
        raise HTTPException(
            status_code=422,
            detail="schedule_id or sales_contract_id required",
        )
    return [InstalmentResponse.model_validate(r) for r in rows]


@router.post(
    "/instalments/", response_model=InstalmentResponse, status_code=201,
)
async def create_instalment(
    data: InstalmentCreate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> InstalmentResponse:
    await _verify_owner_via_schedule(session, data.schedule_id, payload)
    return InstalmentResponse.model_validate(
        await service.create_instalment(data)
    )


@router.get("/instalments/{ins_id}", response_model=InstalmentResponse)
async def get_instalment(
    ins_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> InstalmentResponse:
    await _verify_owner_via_instalment(session, ins_id, payload)
    return InstalmentResponse.model_validate(
        await service.get_instalment(ins_id)
    )


@router.patch("/instalments/{ins_id}", response_model=InstalmentResponse)
async def update_instalment(
    ins_id: uuid.UUID,
    data: InstalmentUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> InstalmentResponse:
    await _verify_owner_via_instalment(session, ins_id, payload)
    return InstalmentResponse.model_validate(
        await service.update_instalment(ins_id, data)
    )


@router.post(
    "/instalments/{ins_id}/mark-paid",
    response_model=InstalmentResponse,
)
async def mark_instalment_paid(
    ins_id: uuid.UUID,
    data: InstalmentMarkPaidRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.instalment.mark_paid")
    ),
) -> InstalmentResponse:
    await _verify_owner_via_instalment(session, ins_id, payload)
    return InstalmentResponse.model_validate(
        await service.mark_instalment_paid(ins_id, data)
    )


@router.post(
    "/instalments/{ins_id}/issue-demand", response_model=InstalmentResponse,
)
async def issue_instalment_demand(
    ins_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.instalment.issue_demand")
    ),
) -> InstalmentResponse:
    await _verify_owner_via_instalment(session, ins_id, payload)
    return InstalmentResponse.model_validate(
        await service.issue_instalment_demand(ins_id)
    )


@router.post(
    "/instalments/{ins_id}/waive", response_model=InstalmentResponse,
)
async def waive_instalment(
    ins_id: uuid.UUID,
    data: InstalmentWaiveRequest,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.instalment.waive")
    ),
) -> InstalmentResponse:
    await _verify_owner_via_instalment(session, ins_id, payload)
    return InstalmentResponse.model_validate(
        await service.waive_instalment(ins_id, data)
    )


@router.post(
    "/instalments/accrue-late-fees",
    response_model=dict,
)
async def accrue_late_fees(
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.instalment.waive")),
) -> dict:
    """Admin/cron endpoint — accrue one day of late fees on all overdue
    instalments. Idempotent on the day-stamp; safe to schedule daily.
    """
    result = await service.accrue_late_fees_daily()
    return {
        "touched_count": result["touched_count"],
        "total_accrued": str(result["total_accrued"]),
    }


# ── ContractParties (multi-buyer junction) ──────────────────────────────


@router.get(
    "/contract-parties/", response_model=list[ContractPartyResponse],
)
async def list_contract_parties(
    session: SessionDep,
    payload: CurrentUserPayload,
    sales_contract_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[ContractPartyResponse]:
    await _verify_owner_via_spa(session, sales_contract_id, payload)
    rows = await service.contract_parties.list_for_contract(sales_contract_id)
    return [ContractPartyResponse.model_validate(r) for r in rows]


@router.post(
    "/contract-parties/",
    response_model=ContractPartyResponse,
    status_code=201,
)
async def add_contract_party(
    data: ContractPartyCreate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.contract_party.add")
    ),
) -> ContractPartyResponse:
    await _verify_owner_via_spa(session, data.sales_contract_id, payload)
    return ContractPartyResponse.model_validate(
        await service.add_contract_party(data)
    )


@router.patch(
    "/contract-parties/{party_id}", response_model=ContractPartyResponse,
)
async def update_contract_party(
    party_id: uuid.UUID,
    data: ContractPartyUpdate,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.contract_party.update_ownership")
    ),
) -> ContractPartyResponse:
    await _verify_owner_via_party(session, party_id, payload)
    return ContractPartyResponse.model_validate(
        await service.update_contract_party(party_id, data)
    )


@router.delete("/contract-parties/{party_id}", status_code=204)
async def remove_contract_party(
    party_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.contract_party.remove")
    ),
) -> None:
    await _verify_owner_via_party(session, party_id, payload)
    await service.remove_contract_party(party_id)


# ════════════════════════════════════════════════════════════════════════
# Task #138 — Broker / Commission / Escrow / PriceMatrix / Phase / Block
# ════════════════════════════════════════════════════════════════════════


def _payload_user_id(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("sub") or payload.get("user_id")
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _payload_tenant_id(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("tenant_id") or payload.get("org_id")
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


# ── Phases ──────────────────────────────────────────────────────────────


@router.get("/phases/", response_model=list[PhaseResponse])
async def list_phases(
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PhaseResponse]:
    rows = await service.phases.list_for_dev_ordered(development_id)
    return [PhaseResponse.model_validate(r) for r in rows]


@router.post("/phases/", response_model=PhaseResponse, status_code=201)
async def create_phase(
    data: PhaseCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PhaseResponse:
    return PhaseResponse.model_validate(await service.create_phase(data))


@router.get("/phases/{phase_id}", response_model=PhaseResponse)
async def get_phase(
    phase_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PhaseResponse:
    return PhaseResponse.model_validate(await service.get_phase(phase_id))


@router.patch("/phases/{phase_id}", response_model=PhaseResponse)
async def update_phase(
    phase_id: uuid.UUID,
    data: PhaseUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PhaseResponse:
    return PhaseResponse.model_validate(
        await service.update_phase(phase_id, data)
    )


@router.delete("/phases/{phase_id}", status_code=204)
async def delete_phase(
    phase_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.get_phase(phase_id)
    await service.phases.delete(phase_id)


# ── Blocks ──────────────────────────────────────────────────────────────


@router.get("/blocks/", response_model=list[BlockResponse])
async def list_blocks(
    phase_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BlockResponse]:
    rows = await service.blocks.list_for_phase_ordered(phase_id)
    return [BlockResponse.model_validate(r) for r in rows]


@router.post("/blocks/", response_model=BlockResponse, status_code=201)
async def create_block(
    data: BlockCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BlockResponse:
    return BlockResponse.model_validate(await service.create_block(data))


@router.get("/blocks/{block_id}", response_model=BlockResponse)
async def get_block(
    block_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BlockResponse:
    return BlockResponse.model_validate(await service.get_block(block_id))


@router.patch("/blocks/{block_id}", response_model=BlockResponse)
async def update_block(
    block_id: uuid.UUID,
    data: BlockUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BlockResponse:
    return BlockResponse.model_validate(
        await service.update_block(block_id, data)
    )


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(
    block_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.get_block(block_id)
    await service.blocks.delete(block_id)


# ── Brokers ─────────────────────────────────────────────────────────────


@router.get("/brokers/", response_model=list[BrokerResponse])
async def list_brokers(
    payload: CurrentUserPayload,
    active_only: bool = Query(default=False),
    jurisdiction: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BrokerResponse]:
    tenant_id = _payload_tenant_id(payload)
    if active_only:
        rows = await service.brokers.list_active(
            tenant_id,
            jurisdiction=jurisdiction,
            offset=offset,
            limit=limit,
        )
    else:
        rows = await service.brokers.list_all(
            tenant_id, offset=offset, limit=limit
        )
    return [BrokerResponse.model_validate(r) for r in rows]


@router.post("/brokers/", response_model=BrokerResponse, status_code=201)
async def create_broker(
    data: BrokerCreate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BrokerResponse:
    # Forcibly bind the broker to the caller's tenant on create (closes
    # cross-tenant tenant_id forgery).
    tenant_id = _payload_tenant_id(payload)
    if tenant_id is not None:
        data = data.model_copy(update={"tenant_id": tenant_id})
    return BrokerResponse.model_validate(await service.create_broker(data))


@router.get("/brokers/{broker_id}", response_model=BrokerResponse)
async def get_broker(
    broker_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BrokerResponse:
    broker = await service.get_broker(broker_id)
    _ensure_broker_owner(broker, payload)
    return BrokerResponse.model_validate(broker)


@router.patch("/brokers/{broker_id}", response_model=BrokerResponse)
async def update_broker(
    broker_id: uuid.UUID,
    data: BrokerUpdate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BrokerResponse:
    broker = await service.get_broker(broker_id)
    _ensure_broker_owner(broker, payload)
    return BrokerResponse.model_validate(
        await service.update_broker(broker_id, data)
    )


@router.delete("/brokers/{broker_id}", status_code=204)
async def delete_broker(
    broker_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    broker = await service.get_broker(broker_id)
    _ensure_broker_owner(broker, payload)
    await service.brokers.delete(broker_id)


@router.post("/brokers/{broker_id}/verify-kyc", response_model=BrokerResponse)
async def verify_broker_kyc(
    broker_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.broker.kyc_verify")),
) -> BrokerResponse:
    broker = await service.get_broker(broker_id)
    _ensure_broker_owner(broker, payload)
    return BrokerResponse.model_validate(
        await service.verify_broker_kyc(broker_id)
    )


def _ensure_broker_owner(broker: Any, payload: dict[str, Any]) -> None:
    """Tenant-isolation gate for brokers.

    Admins bypass. For non-admins, a broker that belongs to a different
    tenant collapses to 404 — never leak existence via 403.
    """
    if payload.get("role") == "admin":
        return
    caller_tenant = _payload_tenant_id(payload)
    broker_tenant = getattr(broker, "tenant_id", None)
    if caller_tenant is None and broker_tenant is None:
        return
    if str(caller_tenant) != str(broker_tenant):
        raise HTTPException(status_code=404, detail="Broker not found")


# ── Commission Agreements ──────────────────────────────────────────────


@router.get(
    "/commission-agreements/", response_model=list[CommissionAgreementResponse],
)
async def list_commission_agreements(
    broker_id: uuid.UUID | None = Query(default=None),
    development_id: uuid.UUID | None = Query(default=None),
    on_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[CommissionAgreementResponse]:
    if broker_id is not None and on_date is not None:
        rows = await service.commission_agreements.list_active_for_broker(
            broker_id, on_date,
        )
    elif development_id is not None and on_date is not None:
        rows = await service.commission_agreements.list_matching(
            development_id=development_id,
            on_date=on_date,
            accrual_trigger="spa_signed",
        )
    elif broker_id is not None:
        # All agreements for a broker (any status).
        from sqlalchemy import select

        from app.modules.property_dev.models import (
            CommissionAgreement as _CA,
        )

        rs = await service.session.execute(
            select(_CA).where(_CA.broker_id == broker_id).order_by(
                _CA.created_at.desc()
            )
        )
        rows = list(rs.scalars().all())
    else:
        rows = []
    return [CommissionAgreementResponse.model_validate(r) for r in rows]


@router.post(
    "/commission-agreements/",
    response_model=CommissionAgreementResponse,
    status_code=201,
)
async def create_commission_agreement(
    data: CommissionAgreementCreate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> CommissionAgreementResponse:
    broker = await service.get_broker(data.broker_id)
    _ensure_broker_owner(broker, payload)
    return CommissionAgreementResponse.model_validate(
        await service.create_agreement(data)
    )


@router.get(
    "/commission-agreements/{agreement_id}",
    response_model=CommissionAgreementResponse,
)
async def get_commission_agreement(
    agreement_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> CommissionAgreementResponse:
    agreement = await service.get_agreement(agreement_id)
    broker = await service.get_broker(agreement.broker_id)
    _ensure_broker_owner(broker, payload)
    return CommissionAgreementResponse.model_validate(agreement)


@router.patch(
    "/commission-agreements/{agreement_id}",
    response_model=CommissionAgreementResponse,
)
async def update_commission_agreement(
    agreement_id: uuid.UUID,
    data: CommissionAgreementUpdate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> CommissionAgreementResponse:
    agreement = await service.get_agreement(agreement_id)
    broker = await service.get_broker(agreement.broker_id)
    _ensure_broker_owner(broker, payload)
    return CommissionAgreementResponse.model_validate(
        await service.update_agreement(agreement_id, data)
    )


@router.delete("/commission-agreements/{agreement_id}", status_code=204)
async def delete_commission_agreement(
    agreement_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    agreement = await service.get_agreement(agreement_id)
    broker = await service.get_broker(agreement.broker_id)
    _ensure_broker_owner(broker, payload)
    await service.commission_agreements.delete(agreement_id)


# ── Commission Accruals ────────────────────────────────────────────────


@router.get(
    "/commission-accruals/", response_model=list[CommissionAccrualResponse],
)
async def list_commission_accruals(
    broker_id: uuid.UUID = Query(...),
    state: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[CommissionAccrualResponse]:
    broker = await service.get_broker(broker_id)
    _ensure_broker_owner(broker, payload or {})
    rows = await service.commission_accruals.list_for_broker(
        broker_id, state=state, offset=offset, limit=limit,
    )
    return [CommissionAccrualResponse.model_validate(r) for r in rows]


@router.post(
    "/commission-accruals/{accrual_id}/approve",
    response_model=CommissionAccrualResponse,
)
async def approve_commission_accrual(
    accrual_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.commission.approve")
    ),
) -> CommissionAccrualResponse:
    user_id = _payload_user_id(payload)
    accrual = await service.commission_accruals.get_by_id(accrual_id)
    if accrual is None:
        raise HTTPException(status_code=404, detail="CommissionAccrual not found")
    broker = await service.get_broker(accrual.broker_id)
    _ensure_broker_owner(broker, payload)
    return CommissionAccrualResponse.model_validate(
        await service.approve_commission(accrual_id, user_id)
    )


@router.post(
    "/commission-accruals/{accrual_id}/pay",
    response_model=CommissionAccrualResponse,
)
async def pay_commission_accrual(
    accrual_id: uuid.UUID,
    data: CommissionAccrualPayRequest,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.commission.pay")),
) -> CommissionAccrualResponse:
    user_id = _payload_user_id(payload)
    accrual = await service.commission_accruals.get_by_id(accrual_id)
    if accrual is None:
        raise HTTPException(status_code=404, detail="CommissionAccrual not found")
    broker = await service.get_broker(accrual.broker_id)
    _ensure_broker_owner(broker, payload)
    return CommissionAccrualResponse.model_validate(
        await service.pay_commission(accrual_id, data.payment_ref, user_id)
    )


# ── Escrow Accounts ────────────────────────────────────────────────────


@router.get(
    "/escrow-accounts/", response_model=list[EscrowAccountResponse],
)
async def list_escrow_accounts(
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[EscrowAccountResponse]:
    await service.get_development(development_id)
    rows = await service.escrow_accounts.list_for_development(development_id)
    return [EscrowAccountResponse.model_validate(r) for r in rows]


@router.post(
    "/escrow-accounts/", response_model=EscrowAccountResponse, status_code=201,
)
async def create_escrow_account(
    data: EscrowAccountCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> EscrowAccountResponse:
    return EscrowAccountResponse.model_validate(
        await service.create_escrow_account(data)
    )


@router.get(
    "/escrow-accounts/{account_id}", response_model=EscrowAccountResponse,
)
async def get_escrow_account(
    account_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowAccountResponse:
    return EscrowAccountResponse.model_validate(
        await service.get_escrow_account(account_id)
    )


@router.patch(
    "/escrow-accounts/{account_id}", response_model=EscrowAccountResponse,
)
async def update_escrow_account(
    account_id: uuid.UUID,
    data: EscrowAccountUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> EscrowAccountResponse:
    return EscrowAccountResponse.model_validate(
        await service.update_escrow_account(account_id, data)
    )


@router.delete("/escrow-accounts/{account_id}", status_code=204)
async def delete_escrow_account(
    account_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.get_escrow_account(account_id)
    await service.escrow_accounts.delete(account_id)


@router.get(
    "/escrow-accounts/{account_id}/balance",
    response_model=EscrowBalanceResponse,
)
async def escrow_account_balance(
    account_id: uuid.UUID,
    as_of_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowBalanceResponse:
    payload = await service.compute_escrow_balance(
        account_id, as_of_date=as_of_date,
    )
    return EscrowBalanceResponse(
        escrow_account_id=payload["escrow_account_id"],
        currency=payload["currency"],
        as_of_date=payload["as_of_date"],
        credit_total=payload["credit_total"],
        debit_total=payload["debit_total"],
        balance=payload["balance"],
        transaction_count=payload["transaction_count"],
        unreconciled_count=payload["unreconciled_count"],
    )


# ── Escrow Transactions ────────────────────────────────────────────────


@router.get(
    "/escrow-transactions/", response_model=list[EscrowTransactionResponse],
)
async def list_escrow_transactions(
    escrow_account_id: uuid.UUID = Query(...),
    unreconciled_only: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[EscrowTransactionResponse]:
    await service.get_escrow_account(escrow_account_id)
    if unreconciled_only:
        rows = await service.escrow_transactions.list_unreconciled(
            escrow_account_id
        )
    else:
        rows = await service.escrow_transactions.list_for_account(
            escrow_account_id, offset=offset, limit=limit,
        )
    return [EscrowTransactionResponse.model_validate(r) for r in rows]


@router.post(
    "/escrow-transactions/",
    response_model=EscrowTransactionResponse,
    status_code=201,
)
async def create_escrow_transaction(
    data: EscrowTransactionCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> EscrowTransactionResponse:
    return EscrowTransactionResponse.model_validate(
        await service.create_escrow_transaction(data)
    )


@router.get(
    "/escrow-transactions/{tx_id}", response_model=EscrowTransactionResponse,
)
async def get_escrow_transaction(
    tx_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowTransactionResponse:
    obj = await service.escrow_transactions.get_by_id(tx_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="EscrowTransaction not found")
    return EscrowTransactionResponse.model_validate(obj)


@router.patch(
    "/escrow-transactions/{tx_id}", response_model=EscrowTransactionResponse,
)
async def update_escrow_transaction(
    tx_id: uuid.UUID,
    data: EscrowTransactionUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> EscrowTransactionResponse:
    obj = await service.escrow_transactions.get_by_id(tx_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="EscrowTransaction not found")
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
    if "metadata" in fields:
        fields["metadata_"] = fields.pop("metadata")
    await service.escrow_transactions.update_fields(tx_id, **fields)
    refreshed = await service.escrow_transactions.get_by_id(tx_id)
    return EscrowTransactionResponse.model_validate(refreshed)


@router.delete("/escrow-transactions/{tx_id}", status_code=204)
async def delete_escrow_transaction(
    tx_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    obj = await service.escrow_transactions.get_by_id(tx_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="EscrowTransaction not found")
    await service.escrow_transactions.delete(tx_id)


@router.post(
    "/escrow-transactions/{tx_id}/reconcile",
    response_model=EscrowTransactionResponse,
)
async def reconcile_escrow_transaction(
    tx_id: uuid.UUID,
    data: EscrowTransactionReconcileRequest,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.escrow.reconcile")
    ),
) -> EscrowTransactionResponse:
    return EscrowTransactionResponse.model_validate(
        await service.reconcile_escrow_transaction(
            tx_id, data.bank_reference, _payload_user_id(payload),
        )
    )


# ── Price Matrices ─────────────────────────────────────────────────────


@router.get(
    "/price-matrices/", response_model=list[PriceMatrixResponse],
)
async def list_price_matrices(
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PriceMatrixResponse]:
    await service.get_development(development_id)
    rows = await service.price_matrices.list_for_development(development_id)
    return [PriceMatrixResponse.model_validate(r) for r in rows]


@router.post(
    "/price-matrices/", response_model=PriceMatrixResponse, status_code=201,
)
async def create_price_matrix(
    data: PriceMatrixCreate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PriceMatrixResponse:
    return PriceMatrixResponse.model_validate(
        await service.create_price_matrix(data)
    )


@router.get(
    "/price-matrices/{matrix_id}", response_model=PriceMatrixResponse,
)
async def get_price_matrix(
    matrix_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PriceMatrixResponse:
    return PriceMatrixResponse.model_validate(
        await service.get_price_matrix(matrix_id)
    )


@router.patch(
    "/price-matrices/{matrix_id}", response_model=PriceMatrixResponse,
)
async def update_price_matrix(
    matrix_id: uuid.UUID,
    data: PriceMatrixUpdate,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PriceMatrixResponse:
    return PriceMatrixResponse.model_validate(
        await service.update_price_matrix(matrix_id, data)
    )


@router.delete("/price-matrices/{matrix_id}", status_code=204)
async def delete_price_matrix(
    matrix_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.get_price_matrix(matrix_id)
    await service.price_matrices.delete(matrix_id)


@router.post(
    "/price-matrices/{matrix_id}/activate",
    response_model=PriceMatrixResponse,
)
async def activate_price_matrix(
    matrix_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.price_matrix.activate")
    ),
) -> PriceMatrixResponse:
    return PriceMatrixResponse.model_validate(
        await service.activate_price_matrix(matrix_id)
    )


@router.get(
    "/price-matrices/{matrix_id}/preview-on-plot/{plot_id}",
    response_model=PriceMatrixPreviewResponse,
)
async def preview_price_on_plot(
    matrix_id: uuid.UUID,
    plot_id: uuid.UUID,
    on_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PriceMatrixPreviewResponse:
    payload = await service.compute_plot_price(
        plot_id, on_date=on_date, matrix_id=matrix_id,
    )
    return PriceMatrixPreviewResponse(**payload)


@router.post(
    "/price-matrices/{matrix_id}/bulk-recompute",
    response_model=PriceMatrixBulkRecomputeResponse,
)
async def bulk_recompute_prices(
    matrix_id: uuid.UUID,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.price_matrix.bulk_recompute")
    ),
) -> PriceMatrixBulkRecomputeResponse:
    matrix = await service.get_price_matrix(matrix_id)
    result = await service.bulk_recompute_dev_prices(matrix.development_id)
    return PriceMatrixBulkRecomputeResponse(**result)


# ── Regulator reports ──────────────────────────────────────────────────


@router.get(
    "/regulator-reports/RERA", response_model=RegulatorReportResponse,
)
async def regulator_report_rera(
    dev_id: uuid.UUID = Query(...),
    quarter: str = Query(..., pattern=r"^\d{4}-Q[1-4]$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.regulator_report.generate")
    ),
) -> RegulatorReportResponse:
    payload = await service.generate_regulator_report_RERA(dev_id, quarter)
    return RegulatorReportResponse(**payload)


@router.get(
    "/regulator-reports/MAHARERA", response_model=RegulatorReportResponse,
)
async def regulator_report_maharera(
    dev_id: uuid.UUID = Query(...),
    quarter: str = Query(..., pattern=r"^\d{4}-Q[1-4]$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.regulator_report.generate")
    ),
) -> RegulatorReportResponse:
    payload = await service.generate_regulator_report_MAHARERA(dev_id, quarter)
    return RegulatorReportResponse(**payload)


@router.get(
    "/regulator-reports/214-FZ", response_model=RegulatorReportResponse,
)
async def regulator_report_214fz(
    dev_id: uuid.UUID = Query(...),
    quarter: str = Query(..., pattern=r"^\d{4}-Q[1-4]$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.regulator_report.generate")
    ),
) -> RegulatorReportResponse:
    payload = await service.generate_regulator_report_214FZ(dev_id, quarter)
    return RegulatorReportResponse(**payload)
