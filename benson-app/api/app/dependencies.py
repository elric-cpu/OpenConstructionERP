from .config import Settings
from .storage import OperationsStore, operations_store


def store(settings: Settings) -> OperationsStore:
    return operations_store(settings.resolved_database_url())
