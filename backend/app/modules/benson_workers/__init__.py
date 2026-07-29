"""Benson background worker and provider adapters."""

from app.core.email import register_email_backend
from app.modules.benson_workers.jobs import register_benson_job_handlers
from app.modules.benson_workers.providers import ResendEmailBackend

register_email_backend("resend", ResendEmailBackend)


async def on_startup() -> None:
    register_benson_job_handlers()
