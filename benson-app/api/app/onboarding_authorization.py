from .auth import Principal
from .domain import Role


PROTECTED_DATA_CATEGORIES = {
    "identity_i9",
    "tax",
    "banking",
    "medical_disability",
    "veteran",
}


def can_manage_employee_data(principal: Principal, data_category: str) -> bool:
    if principal.role is Role.OWNER:
        return True
    if principal.role is not Role.ADMIN:
        return False
    return data_category == "general"


def require_manage_employee_data(principal: Principal, data_category: str) -> None:
    if not can_manage_employee_data(principal, data_category):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Onboarding record not found")
