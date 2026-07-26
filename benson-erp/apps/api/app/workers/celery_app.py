from celery import Celery  # type: ignore[import-untyped]
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from app.core.config import settings
from app.core.observability import configure_logging, configure_tracer

configure_logging(settings)
configure_tracer(settings)
CeleryInstrumentor().instrument()

celery_app = Celery(
    "benson-erp",
    broker=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    beat_schedule={
        "dispatch-transactional-outbox": {
            "task": "benson.dispatch_outbox",
            "schedule": 2.0,
        }
    },
    broker_connection_retry_on_startup=True,
    enable_utc=True,
    result_backend=None,
    task_acks_late=True,
    task_ignore_result=True,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    timezone="UTC",
    worker_hijack_root_logger=False,
    worker_prefetch_multiplier=1,
)
