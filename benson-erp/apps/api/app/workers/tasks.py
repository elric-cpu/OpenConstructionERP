import logging
import uuid

from app.core.observability import correlation_scope
from app.workers.async_runner import async_runner
from app.workers.celery_app import celery_app
from app.workers.dispatcher import dispatch_once
from app.workers.processor import process_event

logger = logging.getLogger("benson.worker")


@celery_app.task(name="benson.process_outbox_event")
def process_outbox_event_task(
    tenant_id: str,
    event_id: str,
    correlation_id: str,
) -> None:
    with correlation_scope(correlation_id):
        result = async_runner.run(
            process_event(uuid.UUID(tenant_id), uuid.UUID(event_id))
        )
        logger.info(
            "outbox_event_processed",
            extra={
                "event_id": event_id,
                "outcome": result.outcome,
                "tenant_id": tenant_id,
            },
        )


@celery_app.task(name="benson.dispatch_outbox")
def dispatch_outbox_task() -> int:
    def publish(
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        correlation_id: uuid.UUID,
    ) -> None:
        celery_app.send_task(
            "benson.process_outbox_event",
            args=(str(tenant_id), str(event_id), str(correlation_id)),
        )

    dispatched = async_runner.run(dispatch_once(publish))
    logger.info("outbox_dispatch_completed", extra={"outcome": f"dispatched:{dispatched}"})
    return dispatched
