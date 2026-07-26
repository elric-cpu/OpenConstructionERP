from app.core.security import Principal

EMPLOYEES_MANAGE = "employees.manage"
EMPLOYEES_APPROVE = "employees.approve"
EMPLOYEES_ACTIVATE = "employees.activate"


def require_employee_activation(principal: Principal) -> None:
    if EMPLOYEES_ACTIVATE in principal.permissions or EMPLOYEES_MANAGE in principal.permissions:
        return
    principal.require(EMPLOYEES_ACTIVATE)
