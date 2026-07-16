import json
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from .domain import FIELD_STAFF, Role
from .schedule_domain import (
    SCHEDULE_TRANSITIONS,
    ScheduleEntryCreate,
    ScheduleEntrySummary,
    ScheduleEntryUpdate,
    ScheduleStatusHistorySummary,
    validate_schedule_interval,
)
from .store_base import StoreBase
from .storage_schema import (
    audit_events,
    customers,
    employees,
    jobs,
    schedule_entries,
    schedule_status_history,
)

schedule_write_lock = RLock()


def lock_schedule_job(db: Any, job_id: str) -> None:
    if db.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:job_key))"),
        {"job_key": f"schedule-job:{job_id}"},
    )


class ScheduleConflict(ValueError):
    pass


class ScheduleStaleWrite(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ScheduleStoreMixin(StoreBase):
    def list_schedule_entries(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        actor: str,
        role: Role,
        limit: int,
        offset: int,
    ) -> list[ScheduleEntrySummary]:
        statement = self._schedule_summary_query().where(
            schedule_entries.c.ends_at > _utc(window_start),
            schedule_entries.c.starts_at < _utc(window_end),
        )
        if role is Role.FIELD:
            statement = statement.where(schedule_entries.c.assigned_to == actor)
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    statement.order_by(schedule_entries.c.starts_at)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [self._schedule_summary(row) for row in rows]

    def is_active_delivery_assignee(self, email: str) -> bool:
        with self.engine.connect() as db:
            return bool(
                db.execute(
                    select(employees.c.id).where(
                        employees.c.email == email,
                        employees.c.role.in_(role.value for role in FIELD_STAFF),
                        employees.c.status.in_(("active", "onboarding_complete")),
                    )
                ).first()
            )

    def create_schedule_entry(
        self, entry: ScheduleEntryCreate, *, actor: str
    ) -> ScheduleEntrySummary:
        entry_id = str(uuid4())
        assignee = str(entry.assigned_to).lower()
        starts_at = _utc(entry.starts_at)
        ends_at = _utc(entry.ends_at)
        now = datetime.now(UTC)
        with schedule_write_lock, self.engine.begin() as db:
            lock_schedule_job(db, str(entry.job_id))
            self._lock_assignees(db, {assignee})
            job = (
                db.execute(
                    select(jobs.c.id, jobs.c.status).where(
                        jobs.c.id == str(entry.job_id)
                    )
                )
                .mappings()
                .first()
            )
            if not job:
                raise LookupError("Job not found")
            if job["status"] not in {"planned", "active"}:
                raise ValueError("Only planned or active jobs may be scheduled")
            self._reject_overlap(
                db, assignee=assignee, starts_at=starts_at, ends_at=ends_at
            )
            try:
                db.execute(
                    schedule_entries.insert().values(
                        id=entry_id,
                        job_id=str(entry.job_id),
                        event_type=entry.event_type,
                        status="scheduled",
                        starts_at=starts_at,
                        ends_at=ends_at,
                        timezone=entry.timezone,
                        assigned_to=assignee,
                        version=1,
                        created_by=actor,
                        created_at=now,
                        updated_at=now,
                    )
                )
            except IntegrityError as error:
                self._raise_schedule_integrity(error)
            self._audit(
                db,
                event="schedule.created",
                actor=actor,
                subject_type="schedule_entry",
                subject_id=entry_id,
                payload={
                    "job_id": str(entry.job_id),
                    "event_type": entry.event_type,
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                    "version": 1,
                },
            )
        return self._load_schedule_entry(entry_id)

    def update_schedule_entry(
        self, entry_id: str, change: ScheduleEntryUpdate, *, actor: str
    ) -> ScheduleEntrySummary | None:
        changes = change.model_dump(exclude_unset=True, exclude={"expected_version"})
        if changes.get("assigned_to") is not None:
            changes["assigned_to"] = str(changes["assigned_to"]).lower()
        requested_fields = set(changes)
        with schedule_write_lock, self.engine.begin() as db:
            current = (
                db.execute(
                    select(schedule_entries, jobs.c.status.label("job_status"))
                    .join(jobs, jobs.c.id == schedule_entries.c.job_id)
                    .where(schedule_entries.c.id == entry_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            lock_schedule_job(db, current["job_id"])
            current = (
                db.execute(
                    select(schedule_entries, jobs.c.status.label("job_status"))
                    .join(jobs, jobs.c.id == schedule_entries.c.job_id)
                    .where(schedule_entries.c.id == entry_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            if current["status"] != "scheduled":
                raise ValueError("Only scheduled entries can be edited")
            if current["job_status"] not in {"planned", "active"}:
                raise ValueError("The job is not available for scheduling")
            assignee = changes.get("assigned_to", current["assigned_to"])
            timezone = changes.get("timezone", current["timezone"])
            zone = ZoneInfo(timezone)
            candidate_start = changes.get("starts_at") or _utc(
                current["starts_at"]
            ).astimezone(zone)
            candidate_end = changes.get("ends_at") or _utc(
                current["ends_at"]
            ).astimezone(zone)
            validate_schedule_interval(candidate_start, candidate_end, timezone)
            starts_at = _utc(candidate_start)
            ends_at = _utc(candidate_end)
            before = {
                "event_type": current["event_type"],
                "starts_at": _utc(current["starts_at"]).isoformat(),
                "ends_at": _utc(current["ends_at"]).isoformat(),
                "timezone": current["timezone"],
                "assigned_to": current["assigned_to"],
            }
            after = {
                "event_type": changes.get("event_type", current["event_type"]),
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "timezone": timezone,
                "assigned_to": assignee,
            }
            audit_changes = {
                field: {"from": before[field], "to": after[field]}
                for field in requested_fields
            }
            self._lock_assignees(db, {str(current["assigned_to"]), str(assignee)})
            self._reject_overlap(
                db,
                assignee=str(assignee),
                starts_at=starts_at,
                ends_at=ends_at,
                exclude_id=entry_id,
            )
            changes.update(
                starts_at=starts_at,
                ends_at=ends_at,
                timezone=timezone,
                updated_at=datetime.now(UTC),
                version=change.expected_version + 1,
            )
            try:
                changed = db.execute(
                    update(schedule_entries)
                    .where(
                        schedule_entries.c.id == entry_id,
                        schedule_entries.c.status == "scheduled",
                        schedule_entries.c.version == change.expected_version,
                    )
                    .values(**changes)
                )
            except IntegrityError as error:
                self._raise_schedule_integrity(error)
            if changed.rowcount != 1:
                raise ScheduleStaleWrite(
                    "Schedule entry changed; reload before retrying"
                )
            self._audit(
                db,
                event="schedule.updated",
                actor=actor,
                subject_type="schedule_entry",
                subject_id=entry_id,
                payload={
                    "changes": audit_changes,
                    "from_version": change.expected_version,
                    "to_version": change.expected_version + 1,
                },
            )
        return self._load_schedule_entry(entry_id)

    def transition_schedule_entry(
        self,
        entry_id: str,
        *,
        target: str,
        expected_version: int,
        actor: str,
        restrict_to_assignee: bool,
        note: str,
    ) -> ScheduleEntrySummary | None:
        with schedule_write_lock, self.engine.begin() as db:
            current = (
                db.execute(
                    select(schedule_entries, jobs.c.status.label("job_status"))
                    .join(jobs, jobs.c.id == schedule_entries.c.job_id)
                    .where(schedule_entries.c.id == entry_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            lock_schedule_job(db, current["job_id"])
            current = (
                db.execute(
                    select(schedule_entries, jobs.c.status.label("job_status"))
                    .join(jobs, jobs.c.id == schedule_entries.c.job_id)
                    .where(schedule_entries.c.id == entry_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            if restrict_to_assignee and current["assigned_to"] != actor:
                return None
            if target not in SCHEDULE_TRANSITIONS[current["status"]]:
                raise ValueError(
                    f"Schedule entry cannot move from {current['status']} to {target}"
                )
            if target != "cancelled" and current["job_status"] not in {
                "planned",
                "active",
            }:
                raise ValueError("The job is not available for field delivery")
            changed = db.execute(
                update(schedule_entries)
                .where(
                    schedule_entries.c.id == entry_id,
                    schedule_entries.c.status == current["status"],
                    schedule_entries.c.version == expected_version,
                )
                .values(
                    status=target,
                    version=expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise ScheduleStaleWrite(
                    "Schedule entry changed; reload before retrying"
                )
            history_id = str(uuid4()) if note.strip() else None
            if history_id:
                db.execute(
                    schedule_status_history.insert().values(
                        id=history_id,
                        schedule_entry_id=entry_id,
                        from_status=current["status"],
                        to_status=target,
                        note=note.strip(),
                        actor=actor,
                        occurred_at=datetime.now(UTC),
                    )
                )
            self._audit(
                db,
                event="schedule.status_changed",
                actor=actor,
                subject_type="schedule_entry",
                subject_id=entry_id,
                payload={
                    "from": current["status"],
                    "to": target,
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "history_id": history_id,
                },
            )
        return self._load_schedule_entry(entry_id)

    def list_schedule_status_history(
        self, entry_id: str
    ) -> list[ScheduleStatusHistorySummary] | None:
        with self.engine.connect() as db:
            if not db.execute(
                select(schedule_entries.c.id).where(schedule_entries.c.id == entry_id)
            ).first():
                return None
            rows = (
                db.execute(
                    select(schedule_status_history)
                    .where(schedule_status_history.c.schedule_entry_id == entry_id)
                    .order_by(schedule_status_history.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [
            ScheduleStatusHistorySummary.model_validate(
                {**dict(row), "occurred_at": _utc(row["occurred_at"])}
            )
            for row in rows
        ]

    def list_schedule_audit(
        self,
        entry_id: str,
        *,
        actor: str,
        role: Role,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]] | None:
        with self.engine.connect() as db:
            exists = select(schedule_entries.c.id).where(
                schedule_entries.c.id == entry_id
            )
            if role is Role.FIELD:
                exists = exists.where(schedule_entries.c.assigned_to == actor)
            if not db.execute(exists).first():
                return None
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "schedule_entry",
                        audit_events.c.subject_id == entry_id,
                    )
                    .order_by(
                        audit_events.c.occurred_at.desc(), audit_events.c.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def _load_schedule_entry(self, entry_id: str) -> ScheduleEntrySummary:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    self._schedule_summary_query().where(
                        schedule_entries.c.id == entry_id
                    )
                )
                .mappings()
                .one()
            )
        return self._schedule_summary(row)

    @staticmethod
    def _schedule_summary_query() -> Any:
        return (
            select(
                schedule_entries.c.id,
                schedule_entries.c.job_id,
                schedule_entries.c.event_type,
                schedule_entries.c.status,
                schedule_entries.c.starts_at,
                schedule_entries.c.ends_at,
                schedule_entries.c.timezone,
                schedule_entries.c.assigned_to,
                schedule_entries.c.version,
                schedule_entries.c.created_at,
                schedule_entries.c.updated_at,
                jobs.c.number.label("job_number"),
                jobs.c.title.label("job_title"),
                jobs.c.site_address,
                customers.c.name.label("customer_name"),
            )
            .join(jobs, jobs.c.id == schedule_entries.c.job_id)
            .join(customers, customers.c.id == jobs.c.customer_id)
        )

    @staticmethod
    def _schedule_summary(row: Any) -> ScheduleEntrySummary:
        payload = dict(row)
        for field in ("starts_at", "ends_at", "created_at", "updated_at"):
            payload[field] = _utc(payload[field])
        return ScheduleEntrySummary.model_validate(payload)

    @staticmethod
    def _lock_assignees(db: Any, assignees: set[str]) -> None:
        if db.dialect.name != "postgresql":
            return
        for assignee in sorted(assignees):
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:assignee))"),
                {"assignee": assignee},
            )

    @staticmethod
    def _reject_overlap(
        db: Any,
        *,
        assignee: str,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: str = "",
    ) -> None:
        conflict = select(schedule_entries.c.id).where(
            schedule_entries.c.assigned_to == assignee,
            schedule_entries.c.status.in_(("scheduled", "in_progress")),
            schedule_entries.c.starts_at < ends_at,
            schedule_entries.c.ends_at > starts_at,
        )
        if exclude_id:
            conflict = conflict.where(schedule_entries.c.id != exclude_id)
        if db.execute(conflict.limit(1)).first():
            raise ScheduleConflict("Assignee already has an overlapping event")

    @staticmethod
    def _raise_schedule_integrity(error: IntegrityError) -> None:
        if "schedule_entries_no_overlap" in str(error.orig):
            raise ScheduleConflict(
                "Assignee already has an overlapping event"
            ) from error
        raise error
