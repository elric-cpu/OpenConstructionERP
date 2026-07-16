from functools import lru_cache

from .ai_store import AiStoreMixin
from .customer_store import CustomerStoreMixin
from .employee_document_store import EmployeeDocumentStoreMixin
from .employee_store import EmployeeStoreMixin
from .employee_task_store import EmployeeTaskStoreMixin
from .estimate_store import EstimateStoreMixin
from .lead_store import LeadStoreMixin
from .job_store import JobStoreMixin
from .logistics_store import LogisticsStoreMixin
from .notification_store import NotificationStoreMixin
from .storage_schema import (
    IdempotencyConflict,
    InvalidEmployeeInvite,
    InvalidEmployeeTaskTransition,
    InvalidLeadTransition,
)


class OperationsStore(
    CustomerStoreMixin,
    EstimateStoreMixin,
    JobStoreMixin,
    EmployeeStoreMixin,
    EmployeeTaskStoreMixin,
    EmployeeDocumentStoreMixin,
    NotificationStoreMixin,
    LeadStoreMixin,
    LogisticsStoreMixin,
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
