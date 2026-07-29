"""Celery bootstrap that registers Benson handlers before consuming jobs."""

from app.core.jobs import get_celery_app
from app.modules.benson_workers.jobs import register_benson_job_handlers

register_benson_job_handlers()
celery_app = get_celery_app()

__all__ = ["celery_app"]
