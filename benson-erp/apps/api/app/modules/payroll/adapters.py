from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from app.modules.payroll.exporters import render_export
from app.modules.payroll.models import PayrollExportFormat

SUPPORTED_PROVIDERS = frozenset(
    {
        "ADP",
        "CONSTRUCTION_PAYROLL",
        "CUSTOM",
        "GENERIC",
        "GUSTO",
        "PAYCHEX",
        "QUICKBOOKS_PAYROLL",
        "RIPPLING",
        "SAGE",
        "UKG",
    }
)


class PayrollProvider(ABC):
    name: str

    @abstractmethod
    def validate_period(self, preview: dict[str, Any]) -> list[str]: ...

    @abstractmethod
    def build_export(
        self,
        rows: Sequence[dict[str, Any]],
        export_format: PayrollExportFormat,
    ) -> tuple[bytes, str, str]: ...

    @abstractmethod
    def send_export(self, payroll_export: Any) -> Any: ...

    @abstractmethod
    def import_results(self, provider_response: Any) -> Any: ...

    @abstractmethod
    def reconcile(self, payroll_period: Any) -> Any: ...


class ConfigurablePayrollProvider(PayrollProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    def validate_period(self, preview: dict[str, Any]) -> list[str]:
        exceptions = preview.get("exceptions", [])
        return [str(item.get("message", "Payroll validation failed")) for item in exceptions]

    def build_export(
        self,
        rows: Sequence[dict[str, Any]],
        export_format: PayrollExportFormat,
    ) -> tuple[bytes, str, str]:
        return render_export(rows, export_format)

    def send_export(self, payroll_export: Any) -> Any:
        raise NotImplementedError("Provider transmission requires an approved connection")

    def import_results(self, provider_response: Any) -> Any:
        raise NotImplementedError("Provider result import is not configured")

    def reconcile(self, payroll_period: Any) -> Any:
        raise NotImplementedError("Provider reconciliation is not configured")


def provider_adapter(name: str) -> PayrollProvider:
    normalized = name.strip().upper().replace(" ", "_")
    if normalized not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported payroll provider {name!r}")
    return ConfigurablePayrollProvider(normalized)
