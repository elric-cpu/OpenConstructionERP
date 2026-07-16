from functools import lru_cache

from .ai_store import AiStoreMixin
from .employee_document_store import EmployeeDocumentStoreMixin
from .employee_store import EmployeeStoreMixin
from .employee_task_store import EmployeeTaskStoreMixin
from .lead_store import LeadStoreMixin
from .notification_store import NotificationStoreMixin
from .storage_schema import (
    IdempotencyConflict,
    InvalidEmployeeInvite,
    InvalidEmployeeTaskTransition,
    InvalidLeadTransition,
)


class OperationsStore(
    EmployeeStoreMixin,
    EmployeeTaskStoreMixin,
    EmployeeDocumentStoreMixin,
    NotificationStoreMixin,
    LeadStoreMixin,
    AiStoreMixin,
):
    pass


@lru_cache
def operations_store(database_url: str) -> OperationsStore:
    return OperationsStore(database_url)


__all__ = [
    "IdempotencyConflict",
    "InvalidEmployeeInvite",
    "InvalidEmployeeTaskTransition",
    "InvalidLeadTransition",
    "OperationsStore",
    "operations_store",
]
