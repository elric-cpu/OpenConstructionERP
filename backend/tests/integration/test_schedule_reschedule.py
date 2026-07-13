"""Integration: edit a dependency and reschedule the Gantt (issue #348).

Exercises the new PATCH ``/relationships/{id}`` and POST
``/schedules/{id}/reschedule/`` handlers against a real (async) throwaway
PostgreSQL. The reschedule bulk-writes real date columns and the PATCH
mirror-rebuild calls ``expire_all()`` - neither is reproducible on a fake
session. The owner check is stubbed to a no-op so the test stays on the
handler + CPM engine path, not the JWT/RBAC stack.

The dates are deterministic because 2024-01-01 is a Monday, so the default
Monday-Friday work calendar projects the CPM offsets onto known weekdays.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.schedule import router as schedule_router
from app.modules.schedule.schemas import (
    ActivityCreate,
    RelationshipCreate,
    RelationshipUpdate,
    ScheduleCreate,
)
from app.modules.schedule.service import ScheduleService
from tests._pg import transactional_session


def _by_id(activities: list, activity_id: uuid.UUID):
    return next(a for a in activities if a.id == activity_id)


@pytest.mark.asyncio
async def test_patch_relationship_and_reschedule_moves_successor() -> None:
    async with transactional_session(disable_fks=True) as session:
        service = ScheduleService(session)

        schedule = await service.create_schedule(
            ScheduleCreate(project_id=uuid.uuid4(), name="Reschedule QA", start_date="2024-01-01")
        )
        # Snapshot the id before the first create_relationship expires the ORM
        # object (its mirror rebuild calls session.expire_all(), after which a
        # sync ``schedule.id`` access would trigger an async refresh). The real
        # route takes the id as a path param, so this is a test-only concern.
        schedule_id = schedule.id
        pred = await service.create_activity(
            ActivityCreate(
                schedule_id=schedule_id,
                name="Predecessor",
                start_date="2024-01-01",
                end_date="2024-01-05",  # 5 working days (Mon-Fri)
            )
        )
        succ = await service.create_activity(
            ActivityCreate(
                schedule_id=schedule_id,
                name="Successor",
                start_date="2024-01-01",  # deliberately overlapping the predecessor
                end_date="2024-01-03",  # 3 working days
            )
        )
        pred_id, succ_id = pred.id, succ.id

        # Keep the test focused on the handler + engine, not the JWT/RBAC stack.
        async def _noop_verify(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            return None

        original = schedule_router._verify_schedule_owner
        schedule_router._verify_schedule_owner = _noop_verify  # type: ignore[assignment]
        try:
            created = await schedule_router.create_relationship(
                schedule_id=schedule_id,
                data=RelationshipCreate(
                    predecessor_id=pred_id,
                    successor_id=succ_id,
                    relationship_type="FS",
                    lag_days=0,
                ),
                session=session,
                _user_id=uuid.uuid4(),
                payload={"role": "admin"},
                service=service,
            )
            rel_id = created.id

            # Reschedule moves the successor to the predecessor's finish (over the
            # weekend) and marks the single chain critical; the root keeps its
            # manually set start.
            activities = await schedule_router.reschedule_schedule(
                schedule_id=schedule_id,
                _user_id=uuid.uuid4(),
                payload={"role": "admin"},
                session=session,
                service=service,
            )
            a_pred = _by_id(activities, pred_id)
            a_succ = _by_id(activities, succ_id)
            assert a_pred.start_date == "2024-01-01"  # root: unchanged
            assert a_pred.is_critical is True
            assert a_succ.start_date == "2024-01-08"  # FS + 0 lag lands on Monday
            assert a_succ.end_date == "2024-01-11"
            assert a_succ.is_critical is True

            # PATCH updates the lag; the type stays FS.
            patched = await schedule_router.update_relationship(
                relationship_id=rel_id,
                data=RelationshipUpdate(lag_days=2),
                session=session,
                _user_id=uuid.uuid4(),
                payload={"role": "admin"},
                service=service,
            )
            assert patched.relationship_type == "FS"
            assert patched.lag_days == 2

            # Reschedule again: the 2-day lag pushes the successor two calendar
            # days later.
            activities = await schedule_router.reschedule_schedule(
                schedule_id=schedule_id,
                _user_id=uuid.uuid4(),
                payload={"role": "admin"},
                session=session,
                service=service,
            )
            a_succ = _by_id(activities, succ_id)
            assert a_succ.start_date == "2024-01-10"
            assert a_succ.end_date == "2024-01-15"

            # PATCH also updates the type; the lag is untouched (still 2).
            retyped = await schedule_router.update_relationship(
                relationship_id=rel_id,
                data=RelationshipUpdate(relationship_type="SS"),
                session=session,
                _user_id=uuid.uuid4(),
                payload={"role": "admin"},
                service=service,
            )
            assert retyped.relationship_type == "SS"
            assert retyped.lag_days == 2
        finally:
            schedule_router._verify_schedule_owner = original  # type: ignore[assignment]
