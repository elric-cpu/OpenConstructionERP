import multiprocessing
import os
from datetime import UTC, date, datetime, timedelta
from queue import Empty
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.storage import OperationsStore
from app.storage_schema import customers, estimates, jobs, schedule_entries


def _schema_url(base_url: str, schema: str) -> str:
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    return url.render_as_string(hide_password=False)


def _close_job(
    database_url: str,
    job_id: str,
    barrier: Any,
    results: Any,
) -> None:
    store = OperationsStore(database_url)
    try:
        barrier.wait(timeout=15)
        store.transition_job(
            job_id,
            target="completed",
            actor="office@bensonhomesolutions.com",
            note="Cross-process closeout.",
        )
        results.put(("job", "ok"))
    except Exception as error:
        results.put(("job", type(error).__name__))
    finally:
        store.engine.dispose()


def _start_schedule(
    database_url: str,
    entry_id: str,
    barrier: Any,
    results: Any,
) -> None:
    store = OperationsStore(database_url)
    try:
        barrier.wait(timeout=15)
        store.transition_schedule_entry(
            entry_id,
            target="in_progress",
            expected_version=1,
            actor="field@bensonhomesolutions.com",
            restrict_to_assignee=True,
            note="",
        )
        results.put(("schedule", "ok"))
    except Exception as error:
        results.put(("schedule", type(error).__name__))
    finally:
        store.engine.dispose()


def test_postgres_advisory_lock_serializes_job_close_and_schedule_start() -> None:
    base_url = os.environ.get("BENSON_POSTGRES_TEST_URL", "")
    if not base_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("BENSON_POSTGRES_TEST_URL is not configured")
    schema = f"schedule_lock_{uuid4().hex}"
    admin_engine = create_engine(base_url)
    database_url = _schema_url(base_url, schema)
    store: OperationsStore | None = None
    try:
        with admin_engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        store = OperationsStore(database_url)
        store.initialize_schema()
        now = datetime.now(UTC)
        customer_id = str(uuid4())
        estimate_id = str(uuid4())
        job_id = str(uuid4())
        entry_id = str(uuid4())
        with store.engine.begin() as db:
            db.execute(
                customers.insert().values(
                    id=customer_id,
                    name="Postgres Lock Test",
                    company="",
                    phone="541-555-0100",
                    email=None,
                    billing_address="",
                    service_address="20 Main Street",
                    city="Burns",
                    state="OR",
                    zip_code="97720",
                    notes="",
                    status="active",
                    source_lead_id=None,
                    created_by="test",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(
                estimates.insert().values(
                    id=estimate_id,
                    number=f"EST-{uuid4().hex[:8]}",
                    customer_id=customer_id,
                    title="Lock test estimate",
                    scope_notes="Synthetic scope.",
                    valid_until=date.today() + timedelta(days=30),
                    status="accepted",
                    version=1,
                    subtotal_cents=1_000,
                    total_cents=1_000,
                    created_by="test",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(
                jobs.insert().values(
                    id=job_id,
                    number=f"JOB-{uuid4().hex[:8]}",
                    estimate_id=estimate_id,
                    customer_id=customer_id,
                    title="Lock test job",
                    scope_snapshot="Synthetic scope.",
                    contract_value_cents=1_000,
                    status="active",
                    target_start=None,
                    target_completion=None,
                    assigned_to="field@bensonhomesolutions.com",
                    site_address="20 Main Street",
                    created_by="test",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(
                schedule_entries.insert().values(
                    id=entry_id,
                    job_id=job_id,
                    event_type="work",
                    status="scheduled",
                    starts_at=now + timedelta(days=1),
                    ends_at=now + timedelta(days=1, hours=1),
                    timezone="America/Los_Angeles",
                    assigned_to="field@bensonhomesolutions.com",
                    version=1,
                    created_by="test",
                    created_at=now,
                    updated_at=now,
                )
            )

        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        processes = (
            context.Process(
                target=_close_job,
                args=(database_url, job_id, barrier, results),
            ),
            context.Process(
                target=_start_schedule,
                args=(database_url, entry_id, barrier, results),
            ),
        )
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=20)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            assert process.exitcode == 0
        try:
            outcomes = {results.get(timeout=5) for _ in processes}
        except Empty as error:
            raise AssertionError("PostgreSQL workers did not report results") from error
        assert sorted(result for _, result in outcomes) == ["ValueError", "ok"]

        with store.engine.connect() as db:
            job_status = db.execute(
                select(jobs.c.status).where(jobs.c.id == job_id)
            ).scalar_one()
            entry_status = db.execute(
                select(schedule_entries.c.status).where(
                    schedule_entries.c.id == entry_id
                )
            ).scalar_one()
        assert (job_status, entry_status) in {
            ("completed", "cancelled"),
            ("active", "in_progress"),
        }
    finally:
        if store is not None:
            store.engine.dispose()
        with admin_engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
