from functools import lru_cache

from .ai_store import AiStoreMixin
from .customer_store import CustomerStoreMixin
from .change_order_store import ChangeOrderStoreMixin
from .change_order_evidence_store import ChangeOrderEvidenceStoreMixin
from .employee_document_store import EmployeeDocumentStoreMixin
from .employee_store import EmployeeStoreMixin
from .employee_task_store import EmployeeTaskStoreMixin
from .estimate_store import EstimateStoreMixin
from .field_record_store import FieldRecordStoreMixin
from .lead_store import LeadStoreMixin
from .job_store import JobStoreMixin
from .logistics_store import LogisticsStoreMixin
from .notification_store import NotificationStoreMixin
from .schedule_store import ScheduleStoreMixin
from .storage_schema import (
    IdempotencyConflict,
    InvalidEmployeeInvite,
    InvalidEmployeeTaskTransition,
    InvalidLeadTransition,
)


class OperationsStore(
    CustomerStoreMixin,
    ChangeOrderStoreMixin,
    ChangeOrderEvidenceStoreMixin,
    EstimateStoreMixin,
    JobStoreMixin,
    ScheduleStoreMixin,
    FieldRecordStoreMixin,
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
