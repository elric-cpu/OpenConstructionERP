"""‌⁠‍Property Development API routes.

All routes are RBAC-gated and mounted by the module loader at
``/api/v1/property-dev/`` (slash inferred from module name).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.core.file_signature import (
    ALLOWED_PHOTO_TYPES,
    SIGNATURE_BYTES_REQUIRED,
    FileSignatureMismatch,
    mime_for_signature,
    require as require_signature,
)
from app.dependencies import CurrentUserPayload, RequirePermission, SessionDep
from app.modules.portal.dependencies import RequirePortalSession
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
    PropertyDevHouseTypeCreate,
    PropertyDevHouseTypeResponse,
    PropertyDevHouseTypeUpdate,
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
    WarrantyClaimAssignRequest,
    WarrantyClaimCreate,
    WarrantyClaimResponse,
    WarrantyClaimUpdate,
)
from app.modules.property_dev.schemas import (
    ComplianceDashboardResponse,
    ComplianceRegulatorReportResponse,
    ComplianceRuleResult,
)
from app.modules.property_dev.schemas import (
    BuyerJourneyResponse,
    CashflowWaterfallResponse,
    FunnelConversionResponse,
    InventoryAgeingResponse,
    InventoryHeatmapResponse,
    SalesVelocityResponse,
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentResponse:
    await _verify_owner_via_development(session, dev_id, user_payload)
    obj = await service.get_development(dev_id)
    return DevelopmentResponse.model_validate(obj)


@router.patch("/developments/{dev_id}", response_model=DevelopmentResponse)
async def update_development(
    dev_id: uuid.UUID,
    data: DevelopmentUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> DevelopmentResponse:
    await _verify_owner_via_development(session, dev_id, user_payload)
    obj = await service.update_development(dev_id, data)
    return DevelopmentResponse.model_validate(obj)


@router.delete("/developments/{dev_id}", status_code=204)
async def delete_development(
    dev_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_development(session, dev_id, user_payload)
    await service.delete_development(dev_id)


@router.get(
    "/developments/{dev_id}/dashboard",
    response_model=DevelopmentDashboard,
)
async def development_dashboard(
    dev_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentDashboard:
    await _verify_owner_via_development(session, dev_id, user_payload)
    payload = await service.development_sales_dashboard(dev_id)
    return DevelopmentDashboard.model_validate(payload)


@router.get(
    "/developments/{dev_id}/sales-dashboard",
    response_model=DevelopmentDashboard,
)
async def development_sales_dashboard(
    dev_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> DevelopmentDashboard:
    await _verify_owner_via_development(session, dev_id, user_payload)
    payload = await service.development_sales_dashboard(dev_id)
    return DevelopmentDashboard.model_validate(payload)


# ── Plots ───────────────────────────────────────────────────────────────


@router.get("/plots/", response_model=list[PlotResponse])
async def list_plots(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PlotResponse]:
    # R7 IDOR — gate the parent dev so we can't enumerate other tenants'
    # plots by guessing development UUIDs (the dev_id is a query param).
    await _verify_owner_via_development(session, development_id, user_payload)
    rows, _ = await service.plots.list_for_development(
        development_id, offset=offset, limit=limit, status=status
    )
    return [PlotResponse.model_validate(r) for r in rows]


@router.post("/plots/", response_model=PlotResponse, status_code=201)
async def create_plot(
    data: PlotCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PlotResponse:
    # R7 IDOR — prevent creating a plot under someone else's development.
    await _verify_owner_via_development(session, data.development_id, user_payload)
    obj = await service.create_plot(data)
    return PlotResponse.model_validate(obj)


@router.get("/plots/{plot_id}", response_model=PlotResponse)
async def get_plot(
    plot_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PlotResponse:
    await _verify_owner_via_plot(session, plot_id, user_payload)
    obj = await service.get_plot(plot_id)
    return PlotResponse.model_validate(obj)


@router.patch("/plots/{plot_id}", response_model=PlotResponse)
async def update_plot(
    plot_id: uuid.UUID,
    data: PlotUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PlotResponse:
    await _verify_owner_via_plot(session, plot_id, user_payload)
    obj = await service.update_plot(plot_id, data)
    return PlotResponse.model_validate(obj)


@router.delete("/plots/{plot_id}", status_code=204)
async def delete_plot(
    plot_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_plot(session, plot_id, user_payload)
    await service.delete_plot(plot_id)


@router.post("/plots/{plot_id}/reserve", response_model=PlotResponse)
async def reserve_plot(
    plot_id: uuid.UUID,
    data: PlotReserveRequest,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.reserve_plot")),
) -> PlotResponse:
    await _verify_owner_via_plot(session, plot_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HouseTypeResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    rows = await service.house_types.list_for_development(development_id)
    return [HouseTypeResponse.model_validate(r) for r in rows]


@router.post(
    "/house-types/", response_model=HouseTypeResponse, status_code=201,
)
async def create_house_type(
    data: HouseTypeCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> HouseTypeResponse:
    await _verify_owner_via_development(session, data.development_id, user_payload)
    obj = await service.create_house_type(data)
    return HouseTypeResponse.model_validate(obj)


@router.get("/house-types/{ht_id}", response_model=HouseTypeResponse)
async def get_house_type(
    ht_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HouseTypeResponse:
    await _verify_owner_via_house_type(session, ht_id, user_payload)
    return HouseTypeResponse.model_validate(await service.get_house_type(ht_id))


@router.patch("/house-types/{ht_id}", response_model=HouseTypeResponse)
async def update_house_type(
    ht_id: uuid.UUID,
    data: HouseTypeUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> HouseTypeResponse:
    await _verify_owner_via_house_type(session, ht_id, user_payload)
    obj = await service.update_house_type(ht_id, data)
    return HouseTypeResponse.model_validate(obj)


@router.delete("/house-types/{ht_id}", status_code=204)
async def delete_house_type(
    ht_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_house_type(session, ht_id, user_payload)
    await service.delete_house_type(ht_id)


# ── House Type Catalogue (preset + user-created) ────────────────────────


@router.get(
    "/house-type-catalogue/",
    response_model=list[PropertyDevHouseTypeResponse],
)
async def list_house_type_catalogue(
    payload: CurrentUserPayload,
    country_code: str | None = Query(default=None, max_length=2),
    project_id: uuid.UUID | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PropertyDevHouseTypeResponse]:
    """List preset + (when project_id supplied) tenant-created house types.

    Presets (project_id IS NULL, is_preset=True) are always visible.
    Tenant-created entries are only included when the caller owns the
    project — admins see everything.
    """
    rows = await service.list_house_type_catalogue(
        country_code=country_code,
        project_id=project_id,
        user_payload=payload,
    )
    return [PropertyDevHouseTypeResponse.model_validate(r) for r in rows]


@router.post(
    "/house-type-catalogue/",
    response_model=PropertyDevHouseTypeResponse,
    status_code=201,
)
async def create_house_type_catalogue_entry(
    data: PropertyDevHouseTypeCreate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PropertyDevHouseTypeResponse:
    obj = await service.create_house_type_catalogue_entry(data, user_payload=payload)
    return PropertyDevHouseTypeResponse.model_validate(obj)


@router.get(
    "/house-type-catalogue/{entry_id}",
    response_model=PropertyDevHouseTypeResponse,
)
async def get_house_type_catalogue_entry(
    entry_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PropertyDevHouseTypeResponse:
    obj = await service.get_house_type_catalogue_entry(entry_id, user_payload=payload)
    return PropertyDevHouseTypeResponse.model_validate(obj)


@router.patch(
    "/house-type-catalogue/{entry_id}",
    response_model=PropertyDevHouseTypeResponse,
)
async def update_house_type_catalogue_entry(
    entry_id: uuid.UUID,
    data: PropertyDevHouseTypeUpdate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PropertyDevHouseTypeResponse:
    obj = await service.update_house_type_catalogue_entry(
        entry_id, data, user_payload=payload
    )
    return PropertyDevHouseTypeResponse.model_validate(obj)


@router.delete("/house-type-catalogue/{entry_id}", status_code=204)
async def delete_house_type_catalogue_entry(
    entry_id: uuid.UUID,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await service.delete_house_type_catalogue_entry(entry_id, user_payload=payload)


@router.get(
    "/house-type-variants/", response_model=list[HouseTypeVariantResponse],
)
async def list_variants(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    house_type_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HouseTypeVariantResponse]:
    await _verify_owner_via_house_type(session, house_type_id, user_payload)
    rows = await service.variants.list_for_house_type(house_type_id)
    return [HouseTypeVariantResponse.model_validate(r) for r in rows]


@router.post(
    "/house-type-variants/",
    response_model=HouseTypeVariantResponse,
    status_code=201,
)
async def create_variant(
    data: HouseTypeVariantCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> HouseTypeVariantResponse:
    await _verify_owner_via_house_type(session, data.house_type_id, user_payload)
    return HouseTypeVariantResponse.model_validate(
        await service.create_variant(data)
    )


@router.get(
    "/house-type-variants/{v_id}", response_model=HouseTypeVariantResponse,
)
async def get_variant(
    v_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HouseTypeVariantResponse:
    await _verify_owner_via_variant(session, v_id, user_payload)
    return HouseTypeVariantResponse.model_validate(await service.get_variant(v_id))


@router.patch(
    "/house-type-variants/{v_id}", response_model=HouseTypeVariantResponse,
)
async def update_variant(
    v_id: uuid.UUID,
    data: HouseTypeVariantUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> HouseTypeVariantResponse:
    await _verify_owner_via_variant(session, v_id, user_payload)
    return HouseTypeVariantResponse.model_validate(
        await service.update_variant(v_id, data)
    )


@router.delete("/house-type-variants/{v_id}", status_code=204)
async def delete_variant(
    v_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_variant(session, v_id, user_payload)
    await service.delete_variant(v_id)


# ── Option Groups ───────────────────────────────────────────────────────


@router.get("/option-groups/", response_model=list[BuyerOptionGroupResponse])
async def list_option_groups(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerOptionGroupResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    rows = await service.option_groups.list_for_development(development_id)
    return [BuyerOptionGroupResponse.model_validate(r) for r in rows]


@router.post(
    "/option-groups/", response_model=BuyerOptionGroupResponse, status_code=201,
)
async def create_option_group(
    data: BuyerOptionGroupCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerOptionGroupResponse:
    await _verify_owner_via_development(session, data.development_id, user_payload)
    return BuyerOptionGroupResponse.model_validate(
        await service.create_option_group(data)
    )


@router.get("/option-groups/{g_id}", response_model=BuyerOptionGroupResponse)
async def get_option_group(
    g_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerOptionGroupResponse:
    await _verify_owner_via_option_group(session, g_id, user_payload)
    return BuyerOptionGroupResponse.model_validate(
        await service.get_option_group(g_id)
    )


@router.patch("/option-groups/{g_id}", response_model=BuyerOptionGroupResponse)
async def update_option_group(
    g_id: uuid.UUID,
    data: BuyerOptionGroupUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerOptionGroupResponse:
    await _verify_owner_via_option_group(session, g_id, user_payload)
    return BuyerOptionGroupResponse.model_validate(
        await service.update_option_group(g_id, data)
    )


@router.delete("/option-groups/{g_id}", status_code=204)
async def delete_option_group(
    g_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_option_group(session, g_id, user_payload)
    await service.delete_option_group(g_id)


# ── Options ─────────────────────────────────────────────────────────────


@router.get("/options/", response_model=list[BuyerOptionResponse])
async def list_options(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    group_id: uuid.UUID = Query(...),
    active_only: bool = Query(default=True),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerOptionResponse]:
    await _verify_owner_via_option_group(session, group_id, user_payload)
    rows = await service.options.list_for_group(group_id, active_only=active_only)
    return [BuyerOptionResponse.model_validate(r) for r in rows]


@router.post("/options/", response_model=BuyerOptionResponse, status_code=201)
async def create_option(
    data: BuyerOptionCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerOptionResponse:
    await _verify_owner_via_option_group(session, data.group_id, user_payload)
    return BuyerOptionResponse.model_validate(await service.create_option(data))


@router.get("/options/{o_id}", response_model=BuyerOptionResponse)
async def get_option(
    o_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerOptionResponse:
    await _verify_owner_via_option(session, o_id, user_payload)
    return BuyerOptionResponse.model_validate(await service.get_option(o_id))


@router.patch("/options/{o_id}", response_model=BuyerOptionResponse)
async def update_option(
    o_id: uuid.UUID,
    data: BuyerOptionUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerOptionResponse:
    await _verify_owner_via_option(session, o_id, user_payload)
    return BuyerOptionResponse.model_validate(
        await service.update_option(o_id, data)
    )


@router.delete("/options/{o_id}", status_code=204)
async def delete_option(
    o_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_option(session, o_id, user_payload)
    await service.delete_option(o_id)


# ── Buyers ──────────────────────────────────────────────────────────────


@router.get("/buyers/", response_model=list[BuyerResponse])
async def list_buyers(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BuyerResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    rows, _ = await service.buyers.list_for_development(
        development_id, offset=offset, limit=limit, status=status
    )
    return [BuyerResponse.model_validate(r) for r in rows]


@router.post("/buyers/", response_model=BuyerResponse, status_code=201)
async def create_buyer(
    data: BuyerCreate,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    sync_to_contacts: bool = Query(
        default=True,
        description=(
            "When true (default), the buyer is mirrored to the Contacts "
            "directory and the contact picks up the 'property_dev_buyer' "
            "module tag. Pass false to skip the sync (e.g. for portal-"
            "driven anonymous signups)."
        ),
    ),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerResponse:
    caller = payload.get("sub") if isinstance(payload, dict) else None
    return BuyerResponse.model_validate(
        await service.create_buyer(
            data,
            sync_to_contacts=sync_to_contacts,
            tenant_id=str(caller) if caller else None,
        )
    )


@router.get("/buyers/{b_id}", response_model=BuyerResponse)
async def get_buyer(
    b_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerResponse:
    await _verify_owner_via_buyer(session, b_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_buyer(session, b_id, user_payload)
    await service.delete_buyer(b_id)


@router.post("/buyers/{b_id}/contract", response_model=BuyerResponse)
async def contract_buyer(
    b_id: uuid.UUID,
    data: BuyerContractRequest,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.contract_buyer")),
) -> BuyerResponse:
    await _verify_owner_via_buyer(session, b_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_buyer(session, data.buyer_id, user_payload)
    return BuyerSelectionResponse.model_validate(
        await service.create_selection(data)
    )


@router.get("/selections/{s_id}", response_model=BuyerSelectionResponse)
async def get_selection(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
    return BuyerSelectionResponse.model_validate(await service.get_selection(s_id))


@router.patch("/selections/{s_id}", response_model=BuyerSelectionResponse)
async def update_selection(
    s_id: uuid.UUID,
    data: BuyerSelectionUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
    return BuyerSelectionResponse.model_validate(
        await service.update_selection(s_id, data)
    )


@router.delete("/selections/{s_id}", status_code=204)
async def delete_selection(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_selection(session, s_id, user_payload)
    await service.delete_selection(s_id)


@router.post(
    "/selections/{s_id}/submit", response_model=BuyerSelectionResponse,
)
async def submit_selection(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
    return BuyerSelectionResponse.model_validate(
        await service.submit_selection(s_id)
    )


@router.post(
    "/selections/{s_id}/lock", response_model=BuyerSelectionResponse,
)
async def lock_selection(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lock_selection")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BuyerSelectionItemResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
    return BuyerSelectionItemResponse.model_validate(
        await service.add_selection_item(s_id, data)
    )


@router.delete(
    "/selections/{s_id}/items/{item_id}", status_code=204,
)
async def remove_selection_item(
    s_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> None:
    # ``s_id`` kept for URL clarity; we look up via item itself.
    await _verify_owner_via_selection(session, s_id, user_payload)
    _ = s_id
    await service.remove_selection_item(item_id)


@router.post(
    "/selections/{s_id}/submit-for-production",
    response_model=BuyerSelectionResponse,
)
async def selection_submit_for_production(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lock_selection")),
) -> BuyerSelectionResponse:
    await _verify_owner_via_selection(session, s_id, user_payload)
    sel = await service.get_selection(s_id)
    result = await service.submit_for_production(sel.buyer_id)
    return BuyerSelectionResponse.model_validate(result)


# ── Handovers ───────────────────────────────────────────────────────────


@router.get("/handovers/", response_model=list[HandoverResponse])
async def list_handovers(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    plot_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[HandoverResponse]:
    # IDOR closure: tenant must own the plot before seeing its handovers.
    await _verify_owner_via_plot(session, plot_id, user_payload)
    rows = await service.handovers.list_for_plot(plot_id)
    return [HandoverResponse.model_validate(r) for r in rows]


@router.post("/handovers/", response_model=HandoverResponse, status_code=201)
async def create_handover(
    data: HandoverCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    # IDOR closure: must own the plot before scheduling a handover against it.
    await _verify_owner_via_plot(session, data.plot_id, user_payload)
    return HandoverResponse.model_validate(await service.create_handover(data))


@router.get("/handovers/{h_id}", response_model=HandoverResponse)
async def get_handover(
    h_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> HandoverResponse:
    await _verify_owner_via_handover(session, h_id, user_payload)
    return HandoverResponse.model_validate(await service.get_handover(h_id))


@router.patch("/handovers/{h_id}", response_model=HandoverResponse)
async def update_handover(
    h_id: uuid.UUID,
    data: HandoverUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    await _verify_owner_via_handover(session, h_id, user_payload)
    return HandoverResponse.model_validate(
        await service.update_handover(h_id, data)
    )


@router.delete("/handovers/{h_id}", status_code=204)
async def delete_handover(
    h_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_handover(session, h_id, user_payload)
    await service.delete_handover(h_id)


@router.post("/handovers/{h_id}/complete", response_model=HandoverResponse)
async def complete_handover(
    h_id: uuid.UUID,
    data: HandoverCompleteRequest,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverResponse:
    await _verify_owner_via_handover(session, h_id, user_payload)
    return HandoverResponse.model_validate(
        await service.complete_handover(h_id, data)
    )


# ── Snags ───────────────────────────────────────────────────────────────


@router.get("/snags/", response_model=list[SnagResponse])
async def list_snags(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    handover_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[SnagResponse]:
    await _verify_owner_via_handover(session, handover_id, user_payload)
    rows = await service.snags.list_for_handover(handover_id, status=status)
    return [SnagResponse.model_validate(r) for r in rows]


@router.post("/snags/", response_model=SnagResponse, status_code=201)
async def create_snag(
    data: SnagCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> SnagResponse:
    await _verify_owner_via_handover(session, data.handover_id, user_payload)
    return SnagResponse.model_validate(await service.create_snag(data))


@router.get("/snags/{s_id}", response_model=SnagResponse)
async def get_snag(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> SnagResponse:
    await _verify_owner_via_snag(session, s_id, user_payload)
    return SnagResponse.model_validate(await service.get_snag(s_id))


@router.patch("/snags/{s_id}", response_model=SnagResponse)
async def update_snag(
    s_id: uuid.UUID,
    data: SnagUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    await _verify_owner_via_snag(session, s_id, user_payload)
    return SnagResponse.model_validate(await service.update_snag(s_id, data))


@router.delete("/snags/{s_id}", status_code=204)
async def delete_snag(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_snag(session, s_id, user_payload)
    await service.delete_snag(s_id)


@router.post("/snags/{s_id}/fix", response_model=SnagResponse)
async def fix_snag(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    payload: dict[str, Any] | None = None,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    await _verify_owner_via_snag(session, s_id, user_payload)
    fix_notes = (payload or {}).get("fix_notes")
    return SnagResponse.model_validate(
        await service.mark_snag_fixed(s_id, fix_notes=fix_notes)
    )


@router.post("/snags/{s_id}/wont-fix", response_model=SnagResponse)
async def wont_fix_snag(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    payload: dict[str, Any] | None = None,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    await _verify_owner_via_snag(session, s_id, user_payload)
    fix_notes = (payload or {}).get("fix_notes")
    return SnagResponse.model_validate(
        await service.mark_snag_wont_fix(s_id, fix_notes=fix_notes)
    )


# Directory where snag photos live on disk. Mirrors punchlist's layout.
_SNAG_PHOTOS_DIR = Path("uploads/snag/photos")
_snag_logger = logging.getLogger(__name__)


@router.post("/snags/{s_id}/photos/", response_model=SnagResponse)
async def upload_snag_photo(
    s_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    file: UploadFile = File(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.fix_snag")),
) -> SnagResponse:
    """Upload a photo for a snag.

    Content-type headers are attacker-controlled, so we validate the raw
    magic bytes against :data:`ALLOWED_PHOTO_TYPES` (jpeg, png, gif,
    webp, heic, heif, tiff). SVG and any other format are rejected with
    415. Mirrors the closure in
    :func:`app.modules.punchlist.router.upload_photo`.
    """
    await _verify_owner_via_snag(session, s_id, user_payload)

    try:
        content = await file.read()
    except Exception:
        _snag_logger.exception("Unable to read snag photo upload %s", s_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read uploaded photo",
        )

    try:
        detected = require_signature(
            content[:SIGNATURE_BYTES_REQUIRED],
            ALLOWED_PHOTO_TYPES,
            filename=file.filename,
        )
    except FileSignatureMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    _ = mime_for_signature(detected)  # validated; not stored on Snag yet.

    _SNAG_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "photo.jpg").suffix or ".jpg"
    filename = f"{s_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = _SNAG_PHOTOS_DIR / filename

    try:
        filepath.write_bytes(content)
    except Exception:
        _snag_logger.exception("Unable to save snag photo %s", s_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save photo — storage error",
        )

    photo_path = f"snag/photos/{filename}"
    snag = await service.add_snag_photo(s_id, photo_path)
    return SnagResponse.model_validate(snag)


# ── Warranty Claims ─────────────────────────────────────────────────────


@router.get("/warranty-claims/", response_model=list[WarrantyClaimResponse])
async def list_warranty_claims(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    buyer_id: uuid.UUID | None = Query(default=None),
    plot_id: uuid.UUID | None = Query(default=None),
    development_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[WarrantyClaimResponse]:
    """List warranty claims.

    Supports four scoping modes (mutually exclusive — buyer wins, then
    plot, then development, then project). When NONE are supplied the
    endpoint returns the empty list to avoid an accidental cross-tenant
    enumeration (matches the v3110 ``list_warranty_claims`` behavior).
    """
    if buyer_id is not None:
        await _verify_owner_via_buyer(session, buyer_id, user_payload)
        rows = await service.warranty.list_for_buyer(buyer_id, status=status)
    elif plot_id is not None:
        await _verify_owner_via_plot(session, plot_id, user_payload)
        rows = await service.warranty.list_for_plot(plot_id, status=status)
    elif development_id is not None:
        await _verify_owner_via_development(
            session, development_id, user_payload
        )
        rows = await service.warranty.list_for_development(
            development_id,
            status=status,
            category=category,
            severity=severity,
        )
    elif project_id is not None:
        # Project-level listing — IDOR-gated via the project ownership
        # check that already powers ``_verify_owner_via_plot``.
        from app.modules.projects.repository import ProjectRepository

        proj = await ProjectRepository(session).get_by_id(project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        owner_id = uuid.UUID(str(user_payload["sub"]))
        if proj.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="Resource not found")
        rows = await service.warranty.list_for_project(
            project_id, status=status
        )
    else:
        rows = []
    return [
        await service.warranty_response(r)
        for r in rows
    ]


@router.post(
    "/warranty-claims/", response_model=WarrantyClaimResponse, status_code=201,
)
async def create_warranty_claim(
    data: WarrantyClaimCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_plot(session, data.plot_id, user_payload)
    await _verify_owner_via_buyer(session, data.buyer_id, user_payload)
    return await service.warranty_response(
        await service.raise_warranty_claim(data.plot_id, data.buyer_id, data)
    )


@router.get(
    "/warranty-claims/{w_id}", response_model=WarrantyClaimResponse,
)
async def get_warranty_claim(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(await service.get_warranty(w_id))


@router.patch(
    "/warranty-claims/{w_id}", response_model=WarrantyClaimResponse,
)
async def update_warranty_claim(
    w_id: uuid.UUID,
    data: WarrantyClaimUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(
        await service.update_warranty(w_id, data)
    )


@router.delete("/warranty-claims/{w_id}", status_code=204)
async def delete_warranty_claim(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    await service.delete_warranty(w_id)


@router.post(
    "/warranty-claims/{w_id}/assign",
    response_model=WarrantyClaimResponse,
)
async def assign_warranty_claim(
    w_id: uuid.UUID,
    data: WarrantyClaimAssignRequest,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    """Assign (or unassign with ``null``) a contractor / PM owner."""
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(
        await service.assign_warranty(w_id, data.assigned_to_user_id)
    )


@router.post(
    "/warranty/{w_id}/accept", response_model=WarrantyClaimResponse,
)
async def accept_warranty_claim(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(await service.warranty_accept(w_id))


@router.post(
    "/warranty/{w_id}/reject", response_model=WarrantyClaimResponse,
)
async def reject_warranty_claim(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(await service.warranty_reject(w_id))


@router.post(
    "/warranty/{w_id}/close", response_model=WarrantyClaimResponse,
)
async def close_warranty_claim(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    await _verify_owner_via_warranty(session, w_id, user_payload)
    return await service.warranty_response(await service.warranty_close(w_id))


@router.get("/warranty-claims/{w_id}/pdf")
async def warranty_claim_pdf(
    w_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
):
    """Generate a printable PDF for a warranty claim (legal / insurance).

    Falls back to a plain-text response when the reportlab PDF stack is
    unavailable so the endpoint never 500s the page; mirrors the
    document_templates fallback path.
    """
    from fastapi.responses import Response

    await _verify_owner_via_warranty(session, w_id, user_payload)
    claim = await service.get_warranty(w_id)
    payload = await service.warranty_response(claim)

    lines = [
        "WARRANTY CLAIM",
        "",
        f"Claim ID:       {claim.id}",
        f"Plot ID:        {claim.plot_id}",
        f"Buyer ID:       {claim.buyer_id}",
        f"Handover ID:    {claim.handover_id or '—'}",
        f"Raised at:      {claim.raised_at or '—'}",
        f"Category:       {claim.category}",
        f"Severity:       {claim.severity}",
        f"Status:         {claim.status}",
        f"In warranty:    {'YES' if payload.is_in_warranty else 'NO'}",
        f"SLA deadline:   {claim.sla_deadline or '—'}",
        f"Assigned to:    {claim.assigned_to_user_id or '—'}",
        "",
        "Description:",
        claim.description or "(none)",
        "",
        "Resolution notes:",
        claim.resolution_notes or "(none)",
    ]
    body = "\n".join(lines)

    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as _canvas

        buf = BytesIO()
        c = _canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 10)
        y = 800
        for ln in body.splitlines():
            c.drawString(50, y, ln[:110])
            y -= 14
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = 800
        c.save()
        pdf_bytes = buf.getvalue()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="warranty-claim-{w_id}.pdf"'
                ),
            },
        )
    except Exception:
        # reportlab missing or rendering failed — return the txt fallback
        # so the legal/insurance team still gets something printable.
        return Response(
            content=body.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="warranty-claim-{w_id}.txt"'
                ),
            },
        )


@router.post(
    "/warranty-claims/from-snag/{snag_id}",
    response_model=WarrantyClaimResponse,
    status_code=201,
)
async def create_warranty_claim_from_snag(
    snag_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.process_warranty")),
) -> WarrantyClaimResponse:
    """Promote a snag into a warranty claim (idempotent).

    Useful when a defect identified during/after handover turns out to
    be in-warranty and the buyer-facing process needs to escalate.
    Idempotent: if a claim is already linked via ``source_snag_id``, it
    is returned instead of creating a duplicate.
    """
    from app.modules.property_dev.schemas import WarrantyClaimCreate as _WCreate

    await _verify_owner_via_snag(session, snag_id, user_payload)
    snag = await service.get_snag(snag_id)

    existing = await service.warranty.find_by_source_snag(snag_id)
    if existing is not None:
        return await service.warranty_response(existing)

    # Resolve the buyer: prefer the buyer who raised the snag, else
    # whichever buyer is attached to the plot via the handover chain.
    buyer_id = snag.buyer_id
    handover = await service.get_handover(snag.handover_id)
    plot_id = handover.plot_id
    if buyer_id is None:
        # Best-effort: fall back to any buyer on the plot.
        from sqlalchemy import select as _select

        from app.modules.property_dev.models import Buyer as _Buyer

        row = (
            await session.execute(
                _select(_Buyer).where(_Buyer.plot_id == plot_id).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot raise warranty claim: snag has no buyer link",
            )
        buyer_id = row.id

    severity_map = {"minor": "minor", "major": "major", "critical": "critical"}
    payload = _WCreate(
        plot_id=plot_id,
        buyer_id=buyer_id,
        handover_id=snag.handover_id,
        source_snag_id=snag.id,
        category="defect",
        severity=severity_map.get(snag.severity, "minor"),
        description=snag.description or "(promoted from snag)",
        photos=list(snag.photos or []),
    )
    claim = await service.raise_warranty_claim(plot_id, buyer_id, payload)
    return await service.warranty_response(claim)


# ── Cancel buyer + deposit forfeiture ──────────────────────────────────


@router.post("/buyers/{b_id}/cancel", response_model=DepositForfeitureResponse)
async def cancel_buyer(
    b_id: uuid.UUID,
    data: BuyerCancelRequest,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> DepositForfeitureResponse:
    """‌⁠‍Cancel a buyer + compute jurisdiction-specific deposit forfeiture."""
    await _verify_owner_via_buyer(session, b_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.handover")),
) -> HandoverDocResponse:
    await _verify_owner_via_handover_doc(session, doc_id, user_payload)
    return HandoverDocResponse.model_validate(
        await service.update_handover_doc(doc_id, data)
    )


@router.delete("/handover-docs/{doc_id}", status_code=204)
async def delete_handover_doc(
    doc_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_handover_doc(session, doc_id, user_payload)
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


async def _verify_owner_via_handover(
    session: SessionDep,
    handover_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Handover (handover → plot → development → project).

    Collapses "exists but not yours" to 404. Admins bypass.
    """
    from app.modules.property_dev.repository import HandoverRepository

    handover = await HandoverRepository(session).get_by_id(handover_id)
    if handover is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_plot(session, handover.plot_id, payload)


async def _verify_owner_via_snag(
    session: SessionDep,
    snag_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Snag (snag → handover → plot → development → project)."""
    from app.modules.property_dev.repository import SnagRepository

    snag = await SnagRepository(session).get_by_id(snag_id)
    if snag is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_handover(session, snag.handover_id, payload)


async def _verify_owner_via_warranty(
    session: SessionDep,
    claim_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for WarrantyClaim (claim → plot → development → project)."""
    from app.modules.property_dev.repository import WarrantyClaimRepository

    claim = await WarrantyClaimRepository(session).get_by_id(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_plot(session, claim.plot_id, payload)


async def _verify_owner_via_buyer(
    session: SessionDep,
    buyer_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Buyer (buyer → development → project owner)."""
    from app.modules.property_dev.repository import BuyerRepository

    buyer = await BuyerRepository(session).get_by_id(buyer_id)
    if buyer is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, buyer.development_id, payload)


# ── R7 IDOR helpers (Round-7 audit) ─────────────────────────────────────
#
# These helpers extend the existing _verify_owner_via_* chain to the
# remaining project-scoped entities (house-type, variant, option-group,
# option, selection, handover-doc, phase, block, broker, commission,
# escrow, price-matrix). Each collapses "exists but not yours" to 404
# (never 403) to avoid turning the endpoint into an existence oracle.
# Admins always bypass. Pattern mirrors _verify_owner_via_plot.


async def _verify_owner_via_house_type(
    session: SessionDep,
    ht_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for HouseType (ht → development → project owner)."""
    from app.modules.property_dev.repository import HouseTypeRepository

    ht = await HouseTypeRepository(session).get_by_id(ht_id)
    if ht is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, ht.development_id, payload)


async def _verify_owner_via_variant(
    session: SessionDep,
    v_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for HouseTypeVariant (variant → house_type → dev → project)."""
    from app.modules.property_dev.repository import HouseTypeVariantRepository

    variant = await HouseTypeVariantRepository(session).get_by_id(v_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_house_type(session, variant.house_type_id, payload)


async def _verify_owner_via_option_group(
    session: SessionDep,
    g_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for BuyerOptionGroup (group → development → project)."""
    from app.modules.property_dev.repository import BuyerOptionGroupRepository

    group = await BuyerOptionGroupRepository(session).get_by_id(g_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, group.development_id, payload)


async def _verify_owner_via_option(
    session: SessionDep,
    o_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for BuyerOption (option → group → development → project)."""
    from app.modules.property_dev.repository import BuyerOptionRepository

    option = await BuyerOptionRepository(session).get_by_id(o_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_option_group(session, option.group_id, payload)


async def _verify_owner_via_selection(
    session: SessionDep,
    s_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for BuyerSelection (selection → buyer → development → project)."""
    from app.modules.property_dev.repository import BuyerSelectionRepository

    selection = await BuyerSelectionRepository(session).get_by_id(s_id)
    if selection is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_buyer(session, selection.buyer_id, payload)


async def _verify_owner_via_handover_doc(
    session: SessionDep,
    doc_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for HandoverDoc (doc → handover → plot → dev → project)."""
    from app.modules.property_dev.repository import HandoverDocRepository

    doc = await HandoverDocRepository(session).get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_handover(session, doc.handover_id, payload)


async def _verify_owner_via_phase(
    session: SessionDep,
    phase_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Phase (phase → development → project)."""
    from app.modules.property_dev.repository import PhaseRepository

    phase = await PhaseRepository(session).get_by_id(phase_id)
    if phase is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, phase.development_id, payload)


async def _verify_owner_via_block(
    session: SessionDep,
    block_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Block (block → phase → development → project)."""
    from app.modules.property_dev.repository import BlockRepository

    block = await BlockRepository(session).get_by_id(block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_phase(session, block.phase_id, payload)


async def _verify_owner_via_broker(
    session: SessionDep,
    broker_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for Broker via tenant_id (broker.tenant_id == caller).

    Brokers carry a tenant_id (no project FK); they belong to the user
    who created them. Admins bypass.
    """
    is_admin = payload.get("role") == "admin"
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    from app.modules.property_dev.repository import BrokerRepository

    broker = await BrokerRepository(session).get_by_id(broker_id)
    if broker is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if is_admin:
        return
    if broker.tenant_id is None or str(broker.tenant_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Resource not found")


async def _verify_owner_via_commission_agreement(
    session: SessionDep,
    agreement_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for CommissionAgreement (agreement → broker.tenant_id)."""
    from app.modules.property_dev.repository import (
        CommissionAgreementRepository,
    )

    agreement = await CommissionAgreementRepository(session).get_by_id(
        agreement_id,
    )
    if agreement is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_broker(session, agreement.broker_id, payload)


async def _verify_owner_via_commission_accrual(
    session: SessionDep,
    accrual_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for CommissionAccrual (accrual → broker.tenant_id)."""
    from app.modules.property_dev.repository import (
        CommissionAccrualRepository,
    )

    accrual = await CommissionAccrualRepository(session).get_by_id(accrual_id)
    if accrual is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_broker(session, accrual.broker_id, payload)


async def _verify_owner_via_escrow_account(
    session: SessionDep,
    account_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for EscrowAccount (account → development → project)."""
    from app.modules.property_dev.repository import EscrowAccountRepository

    account = await EscrowAccountRepository(session).get_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, account.development_id, payload)


async def _verify_owner_via_escrow_transaction(
    session: SessionDep,
    tx_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for EscrowTransaction (tx → account → development → project)."""
    from app.modules.property_dev.repository import EscrowTransactionRepository

    tx = await EscrowTransactionRepository(session).get_by_id(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_escrow_account(session, tx.escrow_account_id, payload)


async def _verify_owner_via_price_matrix(
    session: SessionDep,
    matrix_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """IDOR closure for PriceMatrix (matrix → development → project)."""
    from app.modules.property_dev.repository import PriceMatrixRepository

    matrix = await PriceMatrixRepository(session).get_by_id(matrix_id)
    if matrix is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    await _verify_owner_via_development(session, matrix.development_id, payload)


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
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    sync_to_contacts: bool = Query(
        default=True,
        description=(
            "When true (default), the lead is mirrored to the Contacts "
            "directory and the contact picks up the 'property_dev_lead' "
            "module tag. Pass false to skip the sync."
        ),
    ),
    _perm: None = Depends(RequirePermission("property_dev.lead.create")),
) -> LeadResponse:
    caller = payload.get("sub") if isinstance(payload, dict) else None
    return LeadResponse.model_validate(
        await service.create_lead(
            data,
            sync_to_contacts=sync_to_contacts,
            tenant_id=str(caller) if caller else None,
        )
    )


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


@router.get(
    "/leads/{lead_id}/contact",
    summary="Get the Contacts directory entry linked to a Lead",
    description=(
        "Returns the canonical Contact row referenced by ``lead.contact_id`` "
        "(or 404 if the lead is not linked / the linked contact was deleted). "
        "Used by the Lead detail drawer to render the 'Linked Contact' card."
    ),
)
async def get_lead_contact(
    lead_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.lead.read")),
) -> dict[str, Any]:
    """Resolve the contact for ``lead_id`` if linked."""
    await _verify_owner_via_lead(session, lead_id, payload)
    lead = await service.get_lead(lead_id)
    if lead.contact_id is None:
        raise HTTPException(status_code=404, detail="Lead is not linked to a contact")
    from app.modules.contacts.models import Contact as _Contact

    contact = await session.get(_Contact, lead.contact_id)
    if contact is None:
        raise HTTPException(
            status_code=404, detail="Linked contact has been deleted"
        )
    return {
        "id": str(contact.id),
        "contact_type": contact.contact_type,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company_name": contact.company_name,
        "primary_email": contact.primary_email,
        "primary_phone": contact.primary_phone,
        "country_code": contact.country_code,
        "module_tags": list(contact.module_tags or []),
    }


@router.get(
    "/buyers/{b_id}/contact",
    summary="Get the Contacts directory entry linked to a Buyer",
    description=(
        "Returns the canonical Contact row referenced by ``buyer.contact_id`` "
        "(or 404 if the buyer is not linked / the linked contact was "
        "deleted)."
    ),
)
async def get_buyer_contact(
    b_id: uuid.UUID,
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> dict[str, Any]:
    """Resolve the contact for ``b_id`` if linked."""
    await _verify_buyer_owner(session, b_id, payload)
    buyer = await service.get_buyer(b_id)
    if buyer.contact_id is None:
        raise HTTPException(status_code=404, detail="Buyer is not linked to a contact")
    from app.modules.contacts.models import Contact as _Contact

    contact = await session.get(_Contact, buyer.contact_id)
    if contact is None:
        raise HTTPException(
            status_code=404, detail="Linked contact has been deleted"
        )
    return {
        "id": str(contact.id),
        "contact_type": contact.contact_type,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company_name": contact.company_name,
        "primary_email": contact.primary_email,
        "primary_phone": contact.primary_phone,
        "country_code": contact.country_code,
        "module_tags": list(contact.module_tags or []),
    }


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
    plot_id: uuid.UUID | None = Query(default=None),
    development_id: uuid.UUID | None = Query(default=None),
    reservation_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[SalesContractResponse]:
    """List SPAs by plot, development or reservation.

    Exactly one of ``plot_id`` / ``development_id`` / ``reservation_id``
    must be supplied. The top-level "Sales Contracts" tab uses
    ``development_id``; per-plot drawers use ``plot_id``; the reservation
    detail view uses ``reservation_id`` to surface a converted SPA.
    """
    if plot_id is not None:
        await _verify_owner_via_plot(session, plot_id, payload)
        rows = await service.sales_contracts.list_for_plot(
            plot_id, status=status
        )
    elif development_id is not None:
        await _verify_owner_via_development(session, development_id, payload)
        rows = await service.sales_contracts.list_for_development(
            development_id, status=status
        )
    elif reservation_id is not None:
        await _verify_owner_via_reservation(session, reservation_id, payload)
        rows = await service.sales_contracts.list_for_reservation(reservation_id)
        if status is not None:
            rows = [r for r in rows if r.status == status]
    else:
        raise HTTPException(
            status_code=422,
            detail="plot_id, development_id or reservation_id required",
        )
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


@router.get(
    "/payment-schedules/",
    response_model=list[PaymentScheduleResponse],
)
async def list_payment_schedules(
    session: SessionDep,
    payload: CurrentUserPayload,
    sales_contract_id: uuid.UUID | None = Query(default=None),
    development_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PaymentScheduleResponse]:
    """List payment schedules by SPA or by development.

    Backs the top-level "Payment Schedules" tab and the SPA detail panel
    which both need to enumerate schedules without knowing each id.
    """
    if sales_contract_id is not None:
        await _verify_owner_via_spa(session, sales_contract_id, payload)
        existing = await service.payment_schedules.get_for_contract(
            sales_contract_id
        )
        rows = [existing] if existing is not None else []
    elif development_id is not None:
        await _verify_owner_via_development(session, development_id, payload)
        rows = await service.payment_schedules.list_for_development(
            development_id, status=status
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="sales_contract_id or development_id required",
        )
    if status is not None and sales_contract_id is not None:
        rows = [r for r in rows if r.status == status]
    return [PaymentScheduleResponse.model_validate(r) for r in rows]


@router.post(
    "/payment-schedules/from-template",
    response_model=PaymentScheduleResponse,
    status_code=201,
)
async def generate_payment_schedule_from_template(
    body: dict[str, Any],
    session: SessionDep,
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.payment_schedule.activate")
    ),
) -> PaymentScheduleResponse:
    """Generate a payment schedule from a milestone template.

    Body schema (validated inline for flexibility):
        sales_contract_id: UUID                — required.
        template_key: str                      — one of the keys returned
                                                 by GET /payment-schedule-templates/.
                                                 Required.
        start_date: "YYYY-MM-DD"               — optional, defaults to SPA
                                                 signing date or today.
        late_fee_pct: Decimal (0..100)         — optional, default 0.
        grace_period_days: int                 — optional, default 0.

    Behaviour: if a schedule already exists for this SPA and it is in
    ``draft``/``suspended``/``cancelled`` state, its instalments are
    cleared and replaced; if it is ``active``/``completed`` the call
    fails with 409 to avoid clobbering paid lines.
    """
    raw_contract = body.get("sales_contract_id")
    raw_template = body.get("template_key")
    if not raw_contract or not raw_template:
        raise HTTPException(
            status_code=422,
            detail="sales_contract_id and template_key are required",
        )
    try:
        contract_id = uuid.UUID(str(raw_contract))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422, detail="invalid sales_contract_id",
        ) from exc
    await _verify_owner_via_spa(session, contract_id, payload)

    template_key = str(raw_template)
    start_date = body.get("start_date")
    if start_date is not None:
        start_date = str(start_date)
    late_fee_pct = body.get("late_fee_pct")
    grace_period_days = body.get("grace_period_days")
    schedule = await service.generate_payment_schedule_from_template(
        contract_id,
        template_key=template_key,
        start_date=start_date,
        late_fee_pct=late_fee_pct,
        grace_period_days=grace_period_days,
    )
    return PaymentScheduleResponse.model_validate(schedule)


@router.get("/payment-schedule-templates/", response_model=list[dict])
async def list_payment_schedule_templates(
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[dict]:
    """Static catalogue of milestone-based payment schedule templates.

    Templates are pure data — see
    :data:`PropertyDevService.PAYMENT_SCHEDULE_TEMPLATES`.
    """
    return PropertyDevService.payment_schedule_template_catalogue()


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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PhaseResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    rows = await service.phases.list_for_dev_ordered(development_id)
    return [PhaseResponse.model_validate(r) for r in rows]


@router.post("/phases/", response_model=PhaseResponse, status_code=201)
async def create_phase(
    data: PhaseCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PhaseResponse:
    await _verify_owner_via_development(session, data.development_id, user_payload)
    return PhaseResponse.model_validate(await service.create_phase(data))


@router.get("/phases/{phase_id}", response_model=PhaseResponse)
async def get_phase(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PhaseResponse:
    await _verify_owner_via_phase(session, phase_id, user_payload)
    return PhaseResponse.model_validate(await service.get_phase(phase_id))


@router.patch("/phases/{phase_id}", response_model=PhaseResponse)
async def update_phase(
    phase_id: uuid.UUID,
    data: PhaseUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PhaseResponse:
    await _verify_owner_via_phase(session, phase_id, user_payload)
    return PhaseResponse.model_validate(
        await service.update_phase(phase_id, data)
    )


@router.delete("/phases/{phase_id}", status_code=204)
async def delete_phase(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_phase(session, phase_id, user_payload)
    await service.get_phase(phase_id)
    await service.phases.delete(phase_id)


# ── Blocks ──────────────────────────────────────────────────────────────


@router.get("/blocks/", response_model=list[BlockResponse])
async def list_blocks(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    phase_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[BlockResponse]:
    await _verify_owner_via_phase(session, phase_id, user_payload)
    rows = await service.blocks.list_for_phase_ordered(phase_id)
    return [BlockResponse.model_validate(r) for r in rows]


@router.post("/blocks/", response_model=BlockResponse, status_code=201)
async def create_block(
    data: BlockCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> BlockResponse:
    await _verify_owner_via_phase(session, data.phase_id, user_payload)
    return BlockResponse.model_validate(await service.create_block(data))


@router.get("/blocks/{block_id}", response_model=BlockResponse)
async def get_block(
    block_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BlockResponse:
    await _verify_owner_via_block(session, block_id, user_payload)
    return BlockResponse.model_validate(await service.get_block(block_id))


@router.patch("/blocks/{block_id}", response_model=BlockResponse)
async def update_block(
    block_id: uuid.UUID,
    data: BlockUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> BlockResponse:
    await _verify_owner_via_block(session, block_id, user_payload)
    return BlockResponse.model_validate(
        await service.update_block(block_id, data)
    )


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(
    block_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_block(session, block_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[EscrowAccountResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    await service.get_development(development_id)
    rows = await service.escrow_accounts.list_for_development(development_id)
    return [EscrowAccountResponse.model_validate(r) for r in rows]


@router.post(
    "/escrow-accounts/", response_model=EscrowAccountResponse, status_code=201,
)
async def create_escrow_account(
    data: EscrowAccountCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> EscrowAccountResponse:
    await _verify_owner_via_development(session, data.development_id, user_payload)
    return EscrowAccountResponse.model_validate(
        await service.create_escrow_account(data)
    )


@router.get(
    "/escrow-accounts/{account_id}", response_model=EscrowAccountResponse,
)
async def get_escrow_account(
    account_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowAccountResponse:
    await _verify_owner_via_escrow_account(session, account_id, user_payload)
    return EscrowAccountResponse.model_validate(
        await service.get_escrow_account(account_id)
    )


@router.patch(
    "/escrow-accounts/{account_id}", response_model=EscrowAccountResponse,
)
async def update_escrow_account(
    account_id: uuid.UUID,
    data: EscrowAccountUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> EscrowAccountResponse:
    await _verify_owner_via_escrow_account(session, account_id, user_payload)
    return EscrowAccountResponse.model_validate(
        await service.update_escrow_account(account_id, data)
    )


@router.delete("/escrow-accounts/{account_id}", status_code=204)
async def delete_escrow_account(
    account_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_escrow_account(session, account_id, user_payload)
    await service.get_escrow_account(account_id)
    await service.escrow_accounts.delete(account_id)


@router.get(
    "/escrow-accounts/{account_id}/balance",
    response_model=EscrowBalanceResponse,
)
async def escrow_account_balance(
    account_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    as_of_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowBalanceResponse:
    await _verify_owner_via_escrow_account(session, account_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    escrow_account_id: uuid.UUID = Query(...),
    unreconciled_only: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[EscrowTransactionResponse]:
    await _verify_owner_via_escrow_account(
        session, escrow_account_id, user_payload,
    )
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> EscrowTransactionResponse:
    await _verify_owner_via_escrow_account(
        session, data.escrow_account_id, user_payload,
    )
    return EscrowTransactionResponse.model_validate(
        await service.create_escrow_transaction(data)
    )


@router.get(
    "/escrow-transactions/{tx_id}", response_model=EscrowTransactionResponse,
)
async def get_escrow_transaction(
    tx_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> EscrowTransactionResponse:
    await _verify_owner_via_escrow_transaction(session, tx_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> EscrowTransactionResponse:
    await _verify_owner_via_escrow_transaction(session, tx_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_escrow_transaction(session, tx_id, user_payload)
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
    session: SessionDep,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.escrow.reconcile")
    ),
) -> EscrowTransactionResponse:
    await _verify_owner_via_escrow_transaction(session, tx_id, payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> list[PriceMatrixResponse]:
    await _verify_owner_via_development(session, development_id, user_payload)
    await service.get_development(development_id)
    rows = await service.price_matrices.list_for_development(development_id)
    return [PriceMatrixResponse.model_validate(r) for r in rows]


@router.post(
    "/price-matrices/", response_model=PriceMatrixResponse, status_code=201,
)
async def create_price_matrix(
    data: PriceMatrixCreate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> PriceMatrixResponse:
    await _verify_owner_via_development(session, data.development_id, user_payload)
    return PriceMatrixResponse.model_validate(
        await service.create_price_matrix(data)
    )


@router.get(
    "/price-matrices/{matrix_id}", response_model=PriceMatrixResponse,
)
async def get_price_matrix(
    matrix_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PriceMatrixResponse:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
    return PriceMatrixResponse.model_validate(
        await service.get_price_matrix(matrix_id)
    )


@router.patch(
    "/price-matrices/{matrix_id}", response_model=PriceMatrixResponse,
)
async def update_price_matrix(
    matrix_id: uuid.UUID,
    data: PriceMatrixUpdate,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> PriceMatrixResponse:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
    return PriceMatrixResponse.model_validate(
        await service.update_price_matrix(matrix_id, data)
    )


@router.delete("/price-matrices/{matrix_id}", status_code=204)
async def delete_price_matrix(
    matrix_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> None:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
    await service.get_price_matrix(matrix_id)
    await service.price_matrices.delete(matrix_id)


@router.post(
    "/price-matrices/{matrix_id}/activate",
    response_model=PriceMatrixResponse,
)
async def activate_price_matrix(
    matrix_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.price_matrix.activate")
    ),
) -> PriceMatrixResponse:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    on_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> PriceMatrixPreviewResponse:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
    await _verify_owner_via_plot(session, plot_id, user_payload)
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
    session: SessionDep,
    user_payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(
        RequirePermission("property_dev.price_matrix.bulk_recompute")
    ),
) -> PriceMatrixBulkRecomputeResponse:
    await _verify_owner_via_price_matrix(session, matrix_id, user_payload)
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


# ── Document templates (#138 follow-up) ────────────────────────────────


_VALID_DOC_TYPES_HTTP: set[str] = {
    "reservation_receipt",
    "sales_contract",
    "payment_receipt",
    "handover_certificate",
    "warranty_certificate",
    "noc",
}

_SUPPORTED_DOC_LOCALES: set[str] = {"en", "de", "ru", "fr", "ar", "es"}


async def _enforce_propdev_doc_owner(
    service: PropertyDevService,
    payload: dict[str, Any],
    *,
    contract_id: uuid.UUID | None,
    reservation_id: uuid.UUID | None,
    handover_id: uuid.UUID | None,
    instalment_id: uuid.UUID | None,
) -> None:
    """Cross-tenant IDOR closure for document endpoints.

    Resolves the calling user's project ownership against the entity
    referenced in the request. Collapses "doesn't exist" and "exists but
    not yours" into 404 so the endpoint can't be turned into a
    UUID-existence oracle. Admins bypass.
    """
    if payload.get("role") == "admin":
        return
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    owner_id = await service.resolve_development_owner(
        contract_id=contract_id,
        reservation_id=reservation_id,
        handover_id=handover_id,
        instalment_id=instalment_id,
    )
    if owner_id is None or str(owner_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )


def _normalise_locale(locale: str) -> str:
    base = (locale or "en").split("-")[0].lower()
    return base if base in _SUPPORTED_DOC_LOCALES else "en"


def _resolve_doc_type_or_404(doc_type: str) -> str:
    if doc_type not in _VALID_DOC_TYPES_HTTP:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown doc_type '{doc_type}'",
        )
    return doc_type


def _filename_for(doc_type: str, entity_id: uuid.UUID | None) -> str:
    suffix = entity_id.hex[:8] if entity_id is not None else "doc"
    base = {
        "reservation_receipt": "reservation-receipt",
        "sales_contract": "sales-contract",
        "payment_receipt": "payment-receipt",
        "handover_certificate": "handover-certificate",
        "warranty_certificate": "warranty-certificate",
        "noc": "no-objection-certificate",
    }.get(doc_type, "document")
    return f"{base}-{suffix}.pdf"


@router.get("/documents/{doc_type}")
async def stream_propdev_document(
    doc_type: str,
    payload: CurrentUserPayload,
    contract_id: uuid.UUID | None = Query(default=None),
    reservation_id: uuid.UUID | None = Query(default=None),
    handover_id: uuid.UUID | None = Query(default=None),
    instalment_id: uuid.UUID | None = Query(default=None),
    locale: str = Query(default="en"),
    payment_method: str = Query(default=""),
    payment_ref: str | None = Query(default=None),
    requested_by: str = Query(default=""),
    structural_warranty_years: int = Query(default=10, ge=0, le=99),
    finishing_warranty_years: int = Query(default=1, ge=0, le=99),
    noc_validity_days: int = Query(default=30, ge=1, le=365),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> Any:
    """Stream the generated PDF as ``application/pdf``.

    The Content-Disposition header carries a stable, human-friendly
    filename. The endpoint is gated by ``property_dev.read`` and
    enforces cross-tenant IDOR via the owner-resolution helper.
    """
    doc_type = _resolve_doc_type_or_404(doc_type)
    locale = _normalise_locale(locale)
    await _enforce_propdev_doc_owner(
        service,
        payload,
        contract_id=contract_id,
        reservation_id=reservation_id,
        handover_id=handover_id,
        instalment_id=instalment_id,
    )
    pdf_bytes = await service.generate_document(
        doc_type=doc_type,
        contract_id=contract_id,
        reservation_id=reservation_id,
        handover_id=handover_id,
        instalment_id=instalment_id,
        locale=locale,
        payment_method=payment_method,
        payment_ref=payment_ref,
        requested_by=requested_by,
        structural_warranty_years=structural_warranty_years,
        finishing_warranty_years=finishing_warranty_years,
        noc_validity_days=noc_validity_days,
    )
    entity_id = (
        contract_id or reservation_id or handover_id or instalment_id
    )
    filename = _filename_for(doc_type, entity_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Document-Type": doc_type,
            "X-Document-Locale": locale,
        },
    )


@router.post("/documents/preview")
async def preview_propdev_document(
    body: dict[str, Any],
    payload: CurrentUserPayload,
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> dict[str, Any]:
    """Return a base64-encoded preview of the generated PDF.

    Used by the frontend ``DocumentPreviewModal`` so the document can be
    embedded inline without an extra round-trip. Same gating and IDOR
    closure as the streaming endpoint.
    """
    import base64

    doc_type = _resolve_doc_type_or_404(str(body.get("doc_type", "")))
    locale = _normalise_locale(str(body.get("locale", "en")))

    def _uuid(name: str) -> uuid.UUID | None:
        raw = body.get(name)
        if raw is None or raw == "":
            return None
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid UUID for {name}",
            ) from exc

    contract_id = _uuid("contract_id")
    reservation_id = _uuid("reservation_id")
    handover_id = _uuid("handover_id")
    instalment_id = _uuid("instalment_id")

    await _enforce_propdev_doc_owner(
        service,
        payload,
        contract_id=contract_id,
        reservation_id=reservation_id,
        handover_id=handover_id,
        instalment_id=instalment_id,
    )
    pdf_bytes = await service.generate_document(
        doc_type=doc_type,
        contract_id=contract_id,
        reservation_id=reservation_id,
        handover_id=handover_id,
        instalment_id=instalment_id,
        locale=locale,
        payment_method=str(body.get("payment_method", "")),
        payment_ref=body.get("payment_ref"),
        requested_by=str(body.get("requested_by", "")),
        structural_warranty_years=int(body.get("structural_warranty_years", 10)),
        finishing_warranty_years=int(body.get("finishing_warranty_years", 1)),
        noc_validity_days=int(body.get("noc_validity_days", 30)),
    )
    page_count = 0
    try:
        from io import BytesIO as _BIO

        from pypdf import PdfReader as _PdfReader

        page_count = len(_PdfReader(_BIO(pdf_bytes)).pages)
    except Exception:
        page_count = max(1, pdf_bytes.count(b"/Type /Page"))

    return {
        "doc_type": doc_type,
        "locale": locale,
        "size_bytes": len(pdf_bytes),
        "page_count": page_count,
        "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "filename": _filename_for(
            doc_type,
            contract_id or reservation_id or handover_id or instalment_id,
        ),
    }


# ── Document-templates settings catalogue ──────────────────────────────


_DOC_TEMPLATE_CATALOGUE: list[dict[str, Any]] = [
    {
        "doc_type": "reservation_receipt",
        "title": "Reservation Receipt",
        "description": (
            "Issued automatically when a buyer pays the reservation "
            "deposit. Single A4 page, no watermark."
        ),
        "trigger": "POST /reservations/ → deposit recorded",
        "entity": "reservation",
        "pages": "1",
    },
    {
        "doc_type": "sales_contract",
        "title": "Sale-Purchase Agreement (SPA)",
        "description": (
            "Multi-page, multi-buyer aware contract. Auto-injects "
            "jurisdiction clauses (RERA / MAHARERA / 214-FZ / CMA). "
            "DRAFT watermark until status is signed/executed."
        ),
        "trigger": "POST /sales-contracts/ → status transitions",
        "entity": "sales_contract",
        "pages": "3+",
    },
    {
        "doc_type": "payment_receipt",
        "title": "Payment Receipt",
        "description": (
            "Issued per paid instalment. Shows outstanding balance and "
            "milestone reference."
        ),
        "trigger": "POST /instalments/{id}/pay",
        "entity": "instalment",
        "pages": "1",
    },
    {
        "doc_type": "handover_certificate",
        "title": "Handover Certificate",
        "description": (
            "Signed at completion. Lists open snags + keys-handed-over "
            "date so the buyer formally accepts the unit."
        ),
        "trigger": "POST /handovers/{id}/complete",
        "entity": "handover",
        "pages": "1",
    },
    {
        "doc_type": "warranty_certificate",
        "title": "Warranty Certificate",
        "description": (
            "Issued on handover. Default 10y structural + 1y finishing. "
            "Lists exclusions and the claim procedure."
        ),
        "trigger": "GET /documents/warranty_certificate?handover_id=…",
        "entity": "handover",
        "pages": "1",
    },
    {
        "doc_type": "noc",
        "title": "No Objection Certificate",
        "description": (
            "Developer's permission for the buyer to resell. Validity "
            "30 days by default."
        ),
        "trigger": "GET /documents/noc?contract_id=…",
        "entity": "sales_contract",
        "pages": "1",
    },
]


_CUSTOM_TEMPLATES_DIR = Path("uploads/property_dev/custom_templates")
_CUSTOM_TEMPLATE_MAX_MB = 10
_CUSTOM_TEMPLATE_MAX_BYTES = _CUSTOM_TEMPLATE_MAX_MB * 1024 * 1024
_ALLOWED_CUSTOM_TEMPLATE_EXTENSIONS: tuple[str, ...] = (
    ".docx", ".html", ".htm", ".pdf", ".odt", ".md", ".txt", ".xlsx",
)

_BINARY_EXT_TO_SIG: dict[str, frozenset[str]] = {
    ".docx": frozenset({"zip"}),
    ".xlsx": frozenset({"zip"}),
    ".odt": frozenset({"zip"}),
    ".pdf": frozenset({"pdf"}),
    ".html": frozenset({"xml"}),
    ".htm": frozenset({"xml"}),
}
_TEXT_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt"})
_TEXT_NULL_SCAN_BYTES = 1024


def _validate_custom_template_magic(ext: str, content: bytes, filename: str) -> None:
    if ext in _BINARY_EXT_TO_SIG:
        try:
            require_signature(
                content[:SIGNATURE_BYTES_REQUIRED],
                _BINARY_EXT_TO_SIG[ext],
                filename=filename,
            )
        except FileSignatureMismatch as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc
        return
    if ext in _TEXT_EXTENSIONS:
        if b"\x00" in content[:_TEXT_NULL_SCAN_BYTES]:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"File '{filename}' looks binary but the extension '{ext}' "
                    "expects plain text."
                ),
            )
        return
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported extension '{ext}'. Allowed: "
            f"{', '.join(_ALLOWED_CUSTOM_TEMPLATE_EXTENSIONS)}"
        ),
    )
_ALLOWED_CUSTOM_DOC_TYPES: tuple[str, ...] = (
    "custom",
    "reservation_receipt",
    "sales_contract",
    "payment_receipt",
    "handover_certificate",
    "warranty_certificate",
    "noc",
    "snag_report",
    "invoice",
    "payment_reminder",
    "kyc_checklist",
    "brokerage_commission",
)
_ALLOWED_CUSTOM_ENTITIES: tuple[str, ...] = (
    "custom", "reservation", "sales_contract", "instalment", "handover",
    "snag", "broker", "buyer", "plot", "development",
)
_CUSTOM_TEMPLATE_LOG = logging.getLogger(__name__ + ".custom_templates")


# Documentation block for the "{i} Variables" modal in the settings
# page. Kept in code (not a YAML file) because it mirrors the public
# fields of the ORM models below — they move together at refactor time.
_TEMPLATE_VARIABLES_DOCUMENTATION: list[dict[str, Any]] = [
    {
        "group": "development",
        "label": "Development",
        "vars": [
            {"key": "{development.name}", "desc": "Development name"},
            {"key": "{development.code}", "desc": "Short development code"},
            {"key": "{development.country_code}", "desc": "ISO-3166 alpha-2"},
            {"key": "{development.dev_type}", "desc": "residential, mixed_use, …"},
            {"key": "{development.total_area_m2}", "desc": "Total m²"},
            {"key": "{development.currency}", "desc": "ISO-4217 (e.g. EUR)"},
            {"key": "{development.developer_name}", "desc": "Developer entity"},
        ],
    },
    {
        "group": "plot",
        "label": "Plot",
        "vars": [
            {"key": "{plot.plot_number}", "desc": "Plot number / ID"},
            {"key": "{plot.area_m2}", "desc": "Plot area in m²"},
            {"key": "{plot.house_type_label}", "desc": "House-type display label"},
            {"key": "{plot.phase_code}", "desc": "Phase code (metadata)"},
            {"key": "{plot.block_code}", "desc": "Block code (metadata)"},
            {"key": "{plot.currency}", "desc": "Plot's pricing currency"},
        ],
    },
    {
        "group": "buyer",
        "label": "Buyer",
        "vars": [
            {"key": "{buyer.full_name}", "desc": "Full legal name"},
            {"key": "{buyer.email}", "desc": "Primary contact email"},
            {"key": "{buyer.party_role}", "desc": "primary / secondary"},
            {"key": "{buyer.ownership_pct}", "desc": "Ownership percentage"},
        ],
    },
    {
        "group": "reservation",
        "label": "Reservation",
        "vars": [
            {"key": "{reservation.reservation_number}", "desc": "RES-YYYY-NNNN"},
            {"key": "{reservation.deposit_amount}", "desc": "Deposit paid"},
            {"key": "{reservation.expires_at}", "desc": "Reservation expiry"},
            {"key": "{reservation.cooling_off_until}", "desc": "Cooling-off date"},
        ],
    },
    {
        "group": "contract",
        "label": "Sales Contract",
        "vars": [
            {"key": "{contract.contract_number}", "desc": "SPA-YYYY-NNNN"},
            {"key": "{contract.total_value}", "desc": "Total contract value"},
            {"key": "{contract.currency}", "desc": "Contract currency"},
            {"key": "{contract.status}", "desc": "draft / signed / executed"},
            {"key": "{contract.signing_date}", "desc": "ISO date"},
            {"key": "{contract.place}", "desc": "Place of signing"},
        ],
    },
    {
        "group": "handover",
        "label": "Handover",
        "vars": [
            {"key": "{handover.scheduled_at}", "desc": "Planned handover date"},
            {"key": "{handover.completed_at}", "desc": "Actual handover date"},
            {"key": "{handover.keys_handed_over_at}", "desc": "Keys-handed-over date"},
            {"key": "{handover.snag_count}", "desc": "Open snags at handover"},
        ],
    },
    {
        "group": "instalment",
        "label": "Instalment",
        "vars": [
            {"key": "{instalment.sequence}", "desc": "Sequence number"},
            {"key": "{instalment.milestone_label}", "desc": "Milestone label"},
            {"key": "{instalment.due_date}", "desc": "Due date (ISO)"},
            {"key": "{instalment.amount}", "desc": "Instalment amount"},
            {"key": "{instalment.amount_paid}", "desc": "Amount paid"},
        ],
    },
]


@router.get("/document-templates/")
async def list_document_templates(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    development_id: uuid.UUID | None = Query(default=None),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> dict[str, Any]:
    """List property-development document templates.

    Returns the six built-in PDF generators shipped with the platform
    plus any tenant-uploaded custom templates owned by the calling
    user's projects. Also returns the supported locales / jurisdictions
    and a documentation block describing the variables custom
    templates may interpolate.

    Built-in templates themselves are source-of-truth code in
    ``document_templates.py``; this endpoint exposes their metadata so
    the settings UI can render a real catalogue with previews instead
    of an empty stub. Custom templates land in
    ``oe_property_dev_custom_template`` with their files under
    ``uploads/property_dev/custom_templates/``.
    """
    from sqlalchemy import select

    from app.modules.property_dev.document_templates import (
        SUPPORTED_LOCALES,
        SUPPORTED_REGULATORS,
    )
    from app.modules.property_dev.models import PropertyDevCustomTemplate

    # Resolve owning project IDs for the calling user. Admins see every
    # uploaded template; everyone else sees only templates from projects
    # they own. The query is bounded by RBAC + the explicit list of
    # owned project IDs — no cross-tenant leakage.
    is_admin = user_payload.get("role") == "admin"
    user_id = user_payload.get("sub") or user_payload.get("user_id")

    stmt = select(PropertyDevCustomTemplate).order_by(
        PropertyDevCustomTemplate.created_at.desc()
    )
    if not is_admin and user_id is not None:
        from app.modules.projects.models import Project

        proj_stmt = select(Project.id).where(Project.owner_id == user_id)
        owned_ids = (await session.execute(proj_stmt)).scalars().all()
        if not owned_ids:
            stmt = stmt.where(PropertyDevCustomTemplate.id == uuid.UUID(int=0))
        else:
            stmt = stmt.where(
                PropertyDevCustomTemplate.project_id.in_(owned_ids)
            )

    if development_id is not None:
        stmt = stmt.where(
            (PropertyDevCustomTemplate.development_id == development_id)
            | (PropertyDevCustomTemplate.development_id.is_(None))
        )

    rows = (await session.execute(stmt)).scalars().all()
    custom_entries: list[dict[str, Any]] = []
    for row in rows:
        custom_entries.append({
            "id": str(row.id),
            "doc_type": row.doc_type,
            "title": row.name,
            "description": row.description or "",
            "trigger": row.trigger,
            "entity": row.entity,
            "pages": "—",
            "is_custom": True,
            "filename": row.filename,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "development_id": (
                str(row.development_id) if row.development_id else None
            ),
            "project_id": str(row.project_id) if row.project_id else None,
            "created_at": row.created_at.isoformat()
            if row.created_at else None,
        })

    builtin_entries = [
        {**tpl, "is_custom": False} for tpl in _DOC_TEMPLATE_CATALOGUE
    ]

    return {
        "templates": builtin_entries + custom_entries,
        "locales": list(SUPPORTED_LOCALES),
        "regulators": list(SUPPORTED_REGULATORS),
        "variables": _TEMPLATE_VARIABLES_DOCUMENTATION,
        "upload": {
            "allowed_extensions": list(_ALLOWED_CUSTOM_TEMPLATE_EXTENSIONS),
            "max_size_mb": _CUSTOM_TEMPLATE_MAX_MB,
        },
    }


def _validate_custom_template_metadata(
    name: str,
    doc_type: str,
    entity: str,
    trigger: str,
) -> tuple[str, str, str, str]:
    """Validate + normalise the upload's text metadata.

    Raises 422 on any field that's empty, too long, or carries
    characters that wouldn't make sense as a doc_type / entity.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Template name is required",
        )
    if len(name) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Template name must be 200 characters or fewer",
        )
    doc_type = (doc_type or "custom").strip().lower()
    if doc_type not in _ALLOWED_CUSTOM_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown doc_type '{doc_type}'. Allowed: "
                f"{', '.join(_ALLOWED_CUSTOM_DOC_TYPES)}"
            ),
        )
    entity = (entity or "custom").strip().lower()
    if entity not in _ALLOWED_CUSTOM_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown entity '{entity}'. Allowed: "
                f"{', '.join(_ALLOWED_CUSTOM_ENTITIES)}"
            ),
        )
    trigger = (trigger or "manual").strip()
    if len(trigger) > 200:
        trigger = trigger[:200]
    return name, doc_type, entity, trigger


@router.post("/document-templates/upload", status_code=201)
async def upload_custom_document_template(
    session: SessionDep,
    user_payload: CurrentUserPayload,
    file: UploadFile = File(...),
    name: str = "",
    doc_type: str = "custom",
    entity: str = "custom",
    trigger: str = "manual",
    description: str = "",
    project_id: uuid.UUID | None = None,
    development_id: uuid.UUID | None = None,
    _perm: None = Depends(RequirePermission("property_dev.create")),
) -> dict[str, Any]:
    """Upload a tenant-owned custom document template.

    Accepts .docx / .html / .htm / .pdf / .odt / .md / .txt up to 10 MB.
    The file lands in ``uploads/property_dev/custom_templates/`` with a
    UUID-prefixed basename so two uploads with the same original
    filename don't collide. Metadata is persisted to
    ``oe_property_dev_custom_template`` and the row appears alongside
    built-in templates on the settings page.
    """
    from sqlalchemy import select

    from app.modules.projects.models import Project
    from app.modules.property_dev.models import PropertyDevCustomTemplate

    name, doc_type, entity, trigger = _validate_custom_template_metadata(
        name, doc_type, entity, trigger,
    )

    raw_filename = file.filename or "template.bin"
    ext = Path(raw_filename).suffix.lower()
    if ext not in _ALLOWED_CUSTOM_TEMPLATE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported extension '{ext}'. Allowed: "
                f"{', '.join(_ALLOWED_CUSTOM_TEMPLATE_EXTENSIONS)}"
            ),
        )

    try:
        content = await file.read()
    except Exception:
        _CUSTOM_TEMPLATE_LOG.exception("Unable to read template upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read uploaded template",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    if len(content) > _CUSTOM_TEMPLATE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Template exceeds {_CUSTOM_TEMPLATE_MAX_MB} MB limit"
            ),
        )

    _validate_custom_template_magic(ext, content, raw_filename)

    is_admin = user_payload.get("role") == "admin"
    user_id_raw = user_payload.get("sub") or user_payload.get("user_id")
    if user_id_raw is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = uuid.UUID(str(user_id_raw))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid user id")

    resolved_project_id: uuid.UUID | None = None
    if project_id is not None:
        proj = await session.get(Project, project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not is_admin and str(proj.owner_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Project not found")
        resolved_project_id = project_id
    else:
        first_proj = (
            await session.execute(
                select(Project.id)
                .where(Project.owner_id == user_id)
                .limit(1),
            )
        ).scalar_one_or_none()
        if first_proj is None and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No project found for current user. Create a project "
                    "before uploading templates."
                ),
            )
        resolved_project_id = first_proj

    _CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    template_id = uuid.uuid4()
    safe_basename = Path(raw_filename).name
    stored_filename = f"{template_id.hex}_{safe_basename}"
    filepath = _CUSTOM_TEMPLATES_DIR / stored_filename

    try:
        filepath.write_bytes(content)
    except Exception:
        _CUSTOM_TEMPLATE_LOG.exception("Unable to save template upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save template — storage error",
        )

    row = PropertyDevCustomTemplate(
        id=template_id,
        project_id=resolved_project_id,
        development_id=development_id,
        name=name,
        doc_type=doc_type,
        entity=entity,
        trigger=trigger,
        description=description.strip() or None,
        filename=safe_basename,
        storage_path=str(filepath.as_posix()),
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        created_by=user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return {
        "id": str(row.id),
        "doc_type": row.doc_type,
        "title": row.name,
        "description": row.description or "",
        "trigger": row.trigger,
        "entity": row.entity,
        "pages": "—",
        "is_custom": True,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "development_id": (
            str(row.development_id) if row.development_id else None
        ),
        "project_id": (
            str(row.project_id) if row.project_id else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/document-templates/custom/{template_id}", status_code=204)
async def delete_custom_document_template(
    template_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    _perm: None = Depends(RequirePermission("property_dev.delete")),
) -> Response:
    """Delete a tenant-uploaded custom template (file + row).

    404s — never 403s — when the row is owned by a different tenant so
    the endpoint can't be turned into a UUID-existence oracle.
    """
    from app.modules.projects.repository import ProjectRepository
    from app.modules.property_dev.models import PropertyDevCustomTemplate

    row = await session.get(PropertyDevCustomTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    is_admin = user_payload.get("role") == "admin"
    user_id = user_payload.get("sub") or user_payload.get("user_id")
    if not is_admin and row.project_id is not None:
        proj = await ProjectRepository(session).get_by_id(row.project_id)
        if proj is None or str(proj.owner_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Template not found")

    try:
        path = Path(row.storage_path)
        if path.exists():
            path.unlink()
    except Exception:
        _CUSTOM_TEMPLATE_LOG.warning(
            "Could not unlink custom template file at %s", row.storage_path,
            exc_info=True,
        )

    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


@router.get("/document-templates/custom/{template_id}/download")
async def download_custom_document_template(
    template_id: uuid.UUID,
    session: SessionDep,
    user_payload: CurrentUserPayload,
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> Response:
    """Stream a previously-uploaded custom template back to the client.

    Same ownership check as the delete endpoint — 404 (not 403) when
    the caller doesn't own the row.
    """
    from app.modules.projects.repository import ProjectRepository
    from app.modules.property_dev.models import PropertyDevCustomTemplate

    row = await session.get(PropertyDevCustomTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    is_admin = user_payload.get("role") == "admin"
    user_id = user_payload.get("sub") or user_payload.get("user_id")
    if not is_admin and row.project_id is not None:
        proj = await ProjectRepository(session).get_by_id(row.project_id)
        if proj is None or str(proj.owner_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Template not found")

    path = Path(row.storage_path)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail="Template file missing from storage",
        )
    data = path.read_bytes()
    return Response(
        content=data,
        media_type=row.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{row.filename}"'
            ),
        },
    )


@router.post("/document-templates/{doc_type}/sample-preview")
async def sample_preview_document_template(
    doc_type: str,
    body: dict[str, Any],
    _user_payload: CurrentUserPayload,
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> dict[str, Any]:
    """Render a synthetic sample of the template (no real entities).

    Useful for previewing the template look-and-feel from the settings
    page. The generator runs against in-memory stub data so any tenant
    can preview without owning a contract.
    """
    import base64
    import uuid as _uuid
    from datetime import UTC, date, datetime, timedelta
    from decimal import Decimal
    from types import SimpleNamespace

    doc_type = _resolve_doc_type_or_404(doc_type)
    locale = _normalise_locale(str(body.get("locale", "en")))
    regulator = str(body.get("regulator", "NONE")).upper()

    # ── Synthetic entities (just enough for each generator) ──
    now = datetime.now(UTC)
    today = date.today()
    development = SimpleNamespace(
        id=_uuid.uuid4(),
        name="Sample Riverside Gardens",
        code="DEV-SAMPLE",
        metadata_={"regulator": regulator},
        completion_date=(today + timedelta(days=180)).isoformat(),
    )
    plot = SimpleNamespace(
        id=_uuid.uuid4(),
        plot_number="P-101",
        area_m2=Decimal("78.50"),
        currency="EUR",
        house_type_label="Modern Townhouse",
        metadata_={"phase_code": "PH-A", "block_code": "B1"},
    )
    buyers = [
        SimpleNamespace(
            id=_uuid.uuid4(),
            full_name="Jane Sample",
            email="jane.sample@example.com",
        ),
        SimpleNamespace(
            id=_uuid.uuid4(),
            full_name="John Sample",
            email="john.sample@example.com",
        ),
    ]
    reservation = SimpleNamespace(
        id=_uuid.uuid4(),
        reservation_number="RES-2026-0042",
        deposit_amount=Decimal("5000.00"),
        currency="EUR",
        expires_at=(today + timedelta(days=14)).isoformat(),
        cooling_off_until=(today + timedelta(days=10)).isoformat(),
        cooling_off_days=10,
    )
    contract = SimpleNamespace(
        id=_uuid.uuid4(),
        contract_number="SPA-2026-0017",
        total_value=Decimal("420000.00"),
        currency="EUR",
        status="draft",
        place="Berlin",
        signing_date=today.isoformat(),
        metadata_={
            "rera_registration_no": "SAMPLE-RERA-001",
            "escrow_account_no": "DE89-3704-0044-0532-0130-00",
        },
    )
    payment_schedule = SimpleNamespace(currency="EUR")
    instalments = [
        SimpleNamespace(
            sequence=i,
            milestone_label=label,
            milestone_event=label,
            due_date=(today + timedelta(days=30 * i)).isoformat(),
            amount=Decimal(str(amount)),
            amount_paid=Decimal("0"),
        )
        for i, (label, amount) in enumerate(
            [
                ("Booking", 10000),
                ("Foundation", 84000),
                ("Structure", 168000),
                ("Finishing", 105000),
                ("Handover", 53000),
            ],
            start=1,
        )
    ]
    parties = [
        SimpleNamespace(
            buyer_id=buyers[0].id,
            party_role="primary",
            ownership_pct=Decimal("50"),
            full_name=buyers[0].full_name,
            email=buyers[0].email,
        ),
        SimpleNamespace(
            buyer_id=buyers[1].id,
            party_role="secondary",
            ownership_pct=Decimal("50"),
            full_name=buyers[1].full_name,
            email=buyers[1].email,
        ),
    ]
    handover = SimpleNamespace(
        id=_uuid.uuid4(),
        scheduled_at=(today + timedelta(days=120)).isoformat(),
        completed_at=today.isoformat(),
        keys_handed_over_at=today.isoformat(),
    )
    paid_instalment = SimpleNamespace(
        sequence=2,
        milestone_label="Foundation",
        milestone_event="foundation_complete",
        amount=Decimal("84000.00"),
        amount_paid=Decimal("84000.00"),
        paid_at=now.isoformat(),
    )

    # ── Dispatch to the right generator ──
    from app.modules.property_dev.document_templates import (
        render_handover_certificate_pdf,
        render_no_objection_certificate_pdf,
        render_payment_receipt_pdf,
        render_reservation_receipt_pdf,
        render_sales_contract_pdf,
        render_warranty_certificate_pdf,
    )

    if doc_type == "reservation_receipt":
        pdf_bytes = render_reservation_receipt_pdf(
            reservation, plot, development, buyers, locale=locale,
        )
    elif doc_type == "sales_contract":
        pdf_bytes = render_sales_contract_pdf(
            contract,
            payment_schedule,
            instalments,
            parties,
            plot,
            development,
            locale=locale,
            buyer_lookup={b.id: b for b in buyers},
        )
    elif doc_type == "payment_receipt":
        pdf_bytes = render_payment_receipt_pdf(
            paid_instalment,
            contract,
            payment_method="bank_transfer",
            payment_ref="REF-SAMPLE-001",
            locale=locale,
            plot=plot,
            development=development,
        )
    elif doc_type == "handover_certificate":
        pdf_bytes = render_handover_certificate_pdf(
            handover,
            contract,
            snag_count=2,
            plot=plot,
            development=development,
            locale=locale,
        )
    elif doc_type == "warranty_certificate":
        pdf_bytes = render_warranty_certificate_pdf(
            contract,
            handover,
            structural_warranty_years=10,
            finishing_warranty_years=1,
            locale=locale,
            plot=plot,
            development=development,
        )
    else:  # noc
        pdf_bytes = render_no_objection_certificate_pdf(
            contract,
            plot,
            development,
            requested_by="Jane Sample (sample)",
            locale=locale,
        )

    page_count = 0
    try:
        from io import BytesIO as _BIO

        from pypdf import PdfReader as _PdfReader

        page_count = len(_PdfReader(_BIO(pdf_bytes)).pages)
    except Exception:
        page_count = max(1, pdf_bytes.count(b"/Type /Page"))

    return {
        "doc_type": doc_type,
        "locale": locale,
        "regulator": regulator,
        "size_bytes": len(pdf_bytes),
        "page_count": page_count,
        "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "filename": f"sample-{doc_type}-{locale}.pdf",
        "sample": True,
    }


# ── Compliance dashboard + regulator reports (task #139) ───────────────


async def _run_property_dev_validation(
    session: SessionDep, dev_id: uuid.UUID, locale: str = "en",
) -> Any:
    """Execute the ``property_dev`` rule set against a development."""
    from app.core.validation.engine import rule_registry, validation_engine

    # Ensure the rule registry is populated. ``register_builtin_rules`` is
    # idempotent — calling it twice does not duplicate rules.
    if not rule_registry.list_rule_sets().get("property_dev"):
        from app.core.validation.rules import register_builtin_rules

        register_builtin_rules()

    return await validation_engine.validate(
        data={},
        rule_sets=["property_dev"],
        target_type="property_dev_development",
        target_id=str(dev_id),
        project_id=str(dev_id),
        metadata={
            "session": session,
            "development_id": str(dev_id),
            "locale": locale,
        },
    )


def _report_to_response(
    dev_id: uuid.UUID, report: Any,
) -> ComplianceDashboardResponse:
    """Materialise a ``ValidationReport`` into the dashboard response."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    summary = report.summary()
    return ComplianceDashboardResponse(
        development_id=dev_id,
        status=summary["status"],
        score=summary["score"],
        counts=summary["counts"],
        rule_sets=summary["rule_sets"],
        duration_ms=summary["duration_ms"],
        generated_at=_dt.now(_UTC).isoformat(timespec="seconds"),
        results=[
            ComplianceRuleResult(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                severity=r.severity.value,
                category=r.category.value,
                passed=r.passed,
                message=r.message,
                element_ref=r.element_ref,
                details=r.details or {},
                suggestion=r.suggestion,
            )
            for r in report.results
        ],
    )


@router.get(
    "/compliance/dashboard",
    response_model=ComplianceDashboardResponse,
)
async def compliance_dashboard(
    session: SessionDep,
    dev_id: uuid.UUID = Query(...),
    locale: str = Query(default="en", min_length=2, max_length=10),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> ComplianceDashboardResponse:
    """Aggregated traffic-light validation report for one development."""
    # Confirm the development exists (404 instead of empty report).
    svc = PropertyDevService(session)
    dev = await svc.developments.get_by_id(dev_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="development_not_found")
    report = await _run_property_dev_validation(session, dev_id, locale)
    return _report_to_response(dev_id, report)


@router.post(
    "/compliance/run-checks",
    response_model=ComplianceDashboardResponse,
)
async def compliance_run_checks(
    session: SessionDep,
    dev_id: uuid.UUID = Query(...),
    locale: str = Query(default="en", min_length=2, max_length=10),
    _perm: None = Depends(RequirePermission("property_dev.update")),
) -> ComplianceDashboardResponse:
    """Trigger a re-run of the property_dev rule set.

    Mounted as POST because side-effecting downstream subscribers (audit
    log, notifications) treat each invocation as a fresh validation pass.
    Requires ``property_dev.update`` to gate it behind editor RBAC.
    """
    svc = PropertyDevService(session)
    dev = await svc.developments.get_by_id(dev_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="development_not_found")
    report = await _run_property_dev_validation(session, dev_id, locale)
    return _report_to_response(dev_id, report)


@router.get(
    "/compliance/regulator-reports",
    # response_model intentionally omitted — endpoint returns either a
    # streaming Response (PDF/payload bytes) or the
    # ComplianceRegulatorReportResponse JSON envelope depending on `as`.
)
async def compliance_regulator_report(
    session: SessionDep,
    dev_id: uuid.UUID = Query(...),
    regulator: str = Query(...),
    quarter: str = Query(..., pattern=r"^\d{4}-Q[1-4]$"),
    as_: str = Query(
        default="json", alias="as", pattern=r"^(json|pdf|payload)$"
    ),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> Any:
    """Generate a regulator report for a development.

    Query::

        regulator = RERA | MAHARERA | 214FZ | CMA
        quarter   = YYYY-Qn
        as        = json (default - base64'd PDF + payload inline) |
                    pdf  (streaming application/pdf) |
                    payload (streaming application/json or application/xml)
    """
    import base64

    from app.modules.property_dev.regulatory import (
        SUPPORTED_REGULATORS,
        generate_regulator_report,
    )

    svc = PropertyDevService(session)
    dev = await svc.developments.get_by_id(dev_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="development_not_found")
    reg_code = (regulator or "").strip().upper()
    if reg_code not in {"RERA", "MAHARERA", "214FZ", "214-FZ", "214", "CMA"}:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unsupported_regulator:{regulator} "
                f"(supported: {', '.join(SUPPORTED_REGULATORS)})"
            ),
        )
    try:
        report = await generate_regulator_report(
            session, dev_id=dev_id, regulator=reg_code, quarter=quarter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if as_ == "pdf":
        return Response(
            content=report.pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{report.regulator}_{report.quarter}.pdf"'
                ),
            },
        )
    if as_ == "payload":
        media = (
            "application/xml"
            if report.payload_format == "xml"
            else "application/json"
        )
        ext = "xml" if report.payload_format == "xml" else "json"
        return Response(
            content=report.payload_bytes,
            media_type=media,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{report.regulator}_{report.quarter}.{ext}"'
                ),
            },
        )
    return ComplianceRegulatorReportResponse(
        regulator=report.regulator,
        development_id=dev_id,
        quarter=report.quarter,
        generated_at=report.generated_at,
        pdf_base64=base64.b64encode(report.pdf_bytes).decode("ascii"),
        payload_format=report.payload_format,
        payload_base64=base64.b64encode(report.payload_bytes).decode("ascii"),
        summary=report.summary,
    )


# ── Dashboards (task #140) ──────────────────────────────────────────────


@router.get(
    "/dashboards/inventory-heatmap",
    response_model=InventoryHeatmapResponse,
)
async def dashboard_inventory_heatmap(
    session: SessionDep,
    payload: CurrentUserPayload,
    dev_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> InventoryHeatmapResponse:
    """Inventory heatmap grouped by Phase -> Block -> Plot."""
    await _verify_owner_via_development(session, dev_id, payload)
    data = await service.dashboard_inventory_heatmap(dev_id)
    return InventoryHeatmapResponse.model_validate(data)


@router.get(
    "/dashboards/sales-velocity",
    response_model=SalesVelocityResponse,
)
async def dashboard_sales_velocity(
    session: SessionDep,
    payload: CurrentUserPayload,
    dev_id: uuid.UUID = Query(...),
    granularity: str = Query(default="month", pattern=r"^(week|month|quarter)$"),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> SalesVelocityResponse:
    """Sales velocity: SPAs signed by period (week/month/quarter)."""
    await _verify_owner_via_development(session, dev_id, payload)
    data = await service.dashboard_sales_velocity(dev_id, granularity=granularity)
    return SalesVelocityResponse.model_validate(data)


@router.get(
    "/dashboards/cashflow-waterfall",
    response_model=CashflowWaterfallResponse,
)
async def dashboard_cashflow_waterfall(
    session: SessionDep,
    payload: CurrentUserPayload,
    dev_id: uuid.UUID = Query(...),
    start_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    months: int = Query(default=12, ge=1, le=60),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> CashflowWaterfallResponse:
    """Monthly cash-flow: scheduled instalments + actual escrow flows."""
    await _verify_owner_via_development(session, dev_id, payload)
    data = await service.dashboard_cashflow_waterfall(
        dev_id, start_month=start_month, months=months,
    )
    return CashflowWaterfallResponse.model_validate(data)


@router.get(
    "/dashboards/inventory-ageing",
    response_model=InventoryAgeingResponse,
)
async def dashboard_inventory_ageing(
    session: SessionDep,
    payload: CurrentUserPayload,
    dev_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> InventoryAgeingResponse:
    """Days-on-market buckets + reserved-no-contract list."""
    await _verify_owner_via_development(session, dev_id, payload)
    data = await service.dashboard_inventory_ageing(dev_id)
    return InventoryAgeingResponse.model_validate(data)


@router.get(
    "/dashboards/funnel-conversion",
    response_model=FunnelConversionResponse,
)
async def dashboard_funnel_conversion(
    session: SessionDep,
    payload: CurrentUserPayload,
    dev_id: uuid.UUID = Query(...),
    period_days: int = Query(default=90, ge=1, le=365),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> FunnelConversionResponse:
    """5-stage funnel: Lead -> Reservation -> SPA draft -> SPA signed -> Handover."""
    await _verify_owner_via_development(session, dev_id, payload)
    data = await service.dashboard_funnel_conversion(
        dev_id, period_days=period_days,
    )
    return FunnelConversionResponse.model_validate(data)


@router.get(
    "/dashboards/buyer-journey",
    response_model=BuyerJourneyResponse,
)
async def dashboard_buyer_journey(
    session: SessionDep,
    payload: CurrentUserPayload,
    buyer_id: uuid.UUID = Query(...),
    service: PropertyDevService = Depends(_svc),
    _perm: None = Depends(RequirePermission("property_dev.read")),
) -> BuyerJourneyResponse:
    """Cross-entity timeline: Lead -> Reservation -> SPA -> Payments -> Handover -> Warranty."""
    await _verify_buyer_owner(session, buyer_id, payload)
    data = await service.dashboard_buyer_journey(buyer_id)
    return BuyerJourneyResponse.model_validate(data)


# ── Buyer portal (task #156) ────────────────────────────────────────────
#
# Portal-user-facing endpoints, gated by ``RequirePortalSession`` (NOT
# ``RequirePermission``). Buyers see ONLY their own snags + warranty
# claims; cross-buyer enumeration is blocked at the SQL where-clause
# level.


async def _buyers_for_portal_user(
    session: SessionDep, portal_user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Resolve every Buyer row linked to this portal user.

    A single email may have multiple Buyer rows (different developments
    or co-ownership across projects). Returns an empty list when the
    portal user has never been linked to any buyer record.
    """
    from sqlalchemy import select as _select

    from app.modules.property_dev.models import Buyer as _Buyer

    rows = await session.execute(
        _select(_Buyer.id).where(_Buyer.portal_user_id == portal_user_id)
    )
    return [r for (r,) in rows.all()]


@router.get(
    "/portal/me/snags",
    response_model=list[SnagResponse],
)
async def portal_list_my_snags(
    session: SessionDep,
    portal_user: RequirePortalSession,
    status: str | None = Query(default=None),
) -> list[SnagResponse]:
    """List snags the calling buyer raised across every plot they own.

    Returns ``[]`` when the portal user has no linked Buyer rows yet.
    ``Snag.buyer_id`` carries the cross-link; surveyor-raised snags
    (``buyer_id IS NULL``) are intentionally invisible to the portal.
    """
    from sqlalchemy import select as _select

    from app.modules.property_dev.models import Snag as _Snag

    buyer_ids = await _buyers_for_portal_user(session, portal_user.id)
    if not buyer_ids:
        return []

    stmt = _select(_Snag).where(_Snag.buyer_id.in_(buyer_ids))
    if status is not None:
        stmt = stmt.where(_Snag.status == status)
    stmt = stmt.order_by(_Snag.created_at.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()
    return [SnagResponse.model_validate(r) for r in rows]


@router.get(
    "/portal/me/warranty-claims",
    response_model=list[WarrantyClaimResponse],
)
async def portal_list_my_warranty_claims(
    session: SessionDep,
    portal_user: "RequirePortalSession",  # noqa: F821
    status: str | None = Query(default=None),
) -> list[WarrantyClaimResponse]:
    """List warranty claims raised by the calling buyer across every plot."""
    from sqlalchemy import select as _select

    from app.modules.property_dev.models import WarrantyClaim as _WC

    buyer_ids = await _buyers_for_portal_user(session, portal_user.id)
    if not buyer_ids:
        return []

    stmt = _select(_WC).where(_WC.buyer_id.in_(buyer_ids))
    if status is not None:
        stmt = stmt.where(_WC.status == status)
    stmt = stmt.order_by(_WC.created_at.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()
    return [WarrantyClaimResponse.model_validate(r) for r in rows]
