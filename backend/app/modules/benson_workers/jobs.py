"""Benson job-runner handlers registered through the upstream worker registry."""

from __future__ import annotations

from typing import Any

from app.core.email import EmailMessage, get_email_service
from app.core.job_run import JobRun
from app.core.job_runner import register_handler
from app.modules.benson_workers.providers import DirectoryIdentityInput, GoogleDirectoryProvider

PROVISION_DIRECTORY_JOB = "benson.provision_google_directory"
SEND_ACTIVATION_JOB = "benson.send_activation_email"


async def provision_google_directory(_job: JobRun, payload: dict[str, Any]) -> dict[str, str]:
    from app.config import get_settings

    provider = GoogleDirectoryProvider(get_settings())
    identity = await provider.create_identity(
        DirectoryIdentityInput(
            primary_email=str(payload["primary_email"]),
            first_name=str(payload["first_name"]),
            last_name=str(payload["last_name"]),
            recovery_email=str(payload["recovery_email"]),
            temporary_password=str(payload["temporary_password"]),
            org_unit_path=str(payload.get("org_unit_path") or "/"),
        )
    )
    return {"subject_id": identity.subject_id, "primary_email": identity.primary_email}


async def send_activation_email(_job: JobRun, payload: dict[str, Any]) -> dict[str, str]:
    service = get_email_service()
    result = await service.send(
        EmailMessage(
            to=str(payload["personal_email"]),
            subject="Activate your Benson ERP access",
            html_body=str(payload["html_body"]),
            tags=["employee_activation"],
        )
    )
    if not result.ok:
        raise RuntimeError(result.reason)
    return {"backend": result.backend, "delivery": result.reason}


def register_benson_job_handlers() -> None:
    register_handler(PROVISION_DIRECTORY_JOB, provision_google_directory)
    register_handler(SEND_ACTIVATION_JOB, send_activation_email)
