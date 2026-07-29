from app.modules.people.models import Employee


def employee_audit_state(employee: Employee) -> dict[str, str | int | None]:
    return {
        "status": employee.status,
        "company_email": employee.company_email,
        "version": employee.version,
    }
