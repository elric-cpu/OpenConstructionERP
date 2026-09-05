from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from .auth import Principal, require_operations_staff, require_owner
from .config import Settings, get_settings
from .dependencies import store
from .domain import CustomerCreate, CustomerSummary, CustomerUpdate

router = APIRouter(prefix="/api/benson/v1/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSummary])
def list_customers(
    query: str = "",
    include_archived: Annotated[bool, Query()] = False,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[CustomerSummary]:
    return store(settings).list_customers(
        query=query, include_archived=include_archived
    )


@router.post("", response_model=CustomerSummary, status_code=status.HTTP_201_CREATED)
def create_customer(
    customer: CustomerCreate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> CustomerSummary:
    return store(settings).create_customer(customer, actor=principal.email)


@router.get("/{customer_id}/audit")
def customer_audit(
    customer_id: str,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_customer_audit(customer_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return events


@router.post(
    "/from-lead/{lead_id}",
    response_model=CustomerSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_from_lead(
    lead_id: str,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> CustomerSummary:
    try:
        customer = store(settings).create_customer_from_lead(
            lead_id, actor=principal.email
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if customer is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return customer


@router.patch("/{customer_id}", response_model=CustomerSummary)
def update_customer(
    customer_id: str,
    change: CustomerUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> CustomerSummary:
    if not change.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=400, detail="At least one customer change is required"
        )
    customer = store(settings).update_customer(
        customer_id, change, actor=principal.email
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_customer(
    customer_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not store(settings).archive_customer(customer_id, actor=principal.email):
        raise HTTPException(status_code=404, detail="Customer not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
