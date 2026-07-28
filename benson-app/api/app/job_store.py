import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .domain import JobCreateFromEstimate, JobSummary, JobUpdate, Role
from .schedule_store import lock_schedule_job, schedule_write_lock
from .store_base import StoreBase
from .storage_schema import (
    audit_events,
    customers,
    estimates,
    jobs,
    schedule_entries,
    schedule_status_history,
)


class JobStoreMixin(StoreBase):
    def list_jobs(
        self, *, status: str = "", actor: str = "", role: Role | None = None
    ) -> list[JobSummary]:
        statement = select(jobs.c.id)
        if status:
            statement = statement.where(jobs.c.status == status)
        if role is Role.FIELD:
            statement = statement.where(jobs.c.assigned_to == actor)
        with self.engine.connect() as db:
            rows = list(
                db.execute(statement.order_by(jobs.c.updated_at.desc())).scalars()
            )
        return [self._load_job(job_id) for job_id in rows]

    def _load_job(self, job_id: str) -> JobSummary:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(
                        jobs,
                        customers.c.name.label("customer_name"),
                        estimates.c.number.label("estimate_number"),
                    )
                    .join(customers, customers.c.id == jobs.c.customer_id)
                    .join(estimates, estimates.c.id == jobs.c.estimate_id)
                    .where(jobs.c.id == job_id)
                )
                .mappings()
                .one()
            )
        return JobSummary.model_validate(row)

    def create_job_from_estimate(
        self,
        estimate_id: str,
        plan: JobCreateFromEstimate,
        *,
        actor: str,
    ) -> JobSummary:
        job_id = str(uuid4())
        number = f"JOB-{datetime.now(UTC).year}-{job_id[:8].upper()}"
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            estimate = (
                db.execute(
                    select(
                        estimates,
                        customers.c.status.label("customer_status"),
                        customers.c.service_address,
                    )
                    .join(customers, customers.c.id == estimates.c.customer_id)
                    .where(estimates.c.id == estimate_id)
                )
                .mappings()
                .first()
            )
            if not estimate or estimate["status"] != "accepted":
                raise ValueError("Only an accepted estimate can become a job")
            if estimate["customer_status"] != "active":
                raise ValueError("An archived customer cannot start a job")
            if db.execute(
                select(jobs.c.id).where(jobs.c.estimate_id == estimate_id)
            ).first():
                raise ValueError("This estimate already has a job")
            try:
                db.execute(
                    jobs.insert().values(
                        id=job_id,
                        number=number,
                        estimate_id=estimate_id,
                        customer_id=estimate["customer_id"],
                        title=estimate["title"],
                        scope_snapshot=estimate["scope_notes"],
                        contract_value_cents=estimate["total_cents"],
                        approved_change_order_cents=0,
                        billing_eligible_cents=estimate["total_cents"],
                        status="planned",
                        target_start=plan.target_start,
                        target_completion=plan.target_completion,
                        assigned_to=str(plan.assigned_to) if plan.assigned_to else None,
                        site_address=plan.site_address or estimate["service_address"],
                        created_by=actor,
                        created_at=now,
                        updated_at=now,
                    )
                )
            except IntegrityError as error:
                raise ValueError("This estimate already has a job") from error
            self._audit(
                db,
                event="job.created_from_estimate",
                actor=actor,
                subject_type="job",
                subject_id=job_id,
                payload={
                    "estimate_id": estimate_id,
                    "number": number,
                    "contract_value_cents": estimate["total_cents"],
                },
            )
        return self._load_job(job_id)

    def update_job(
        self, job_id: str, change: JobUpdate, *, actor: str
    ) -> JobSummary | None:
        changes = change.model_dump(exclude_unset=True)
        if changes.get("assigned_to") is not None:
            changes["assigned_to"] = str(changes["assigned_to"])
        with schedule_write_lock, self.engine.begin() as db:
            lock_schedule_job(db, job_id)
            current = (
                db.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            )
            if not current or current["status"] in {"completed", "cancelled"}:
                return None
            start = changes.get("target_start", current["target_start"])
            completion = changes.get("target_completion", current["target_completion"])
            if start and completion and completion < start:
                raise ValueError("Target completion cannot precede target start")
            changes["updated_at"] = datetime.now(UTC)
            changed = db.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.status == current["status"])
                .values(**changes)
            )
            if changed.rowcount != 1:
                raise ValueError("Job changed concurrently; reload before retrying")
            self._audit(
                db,
                event="job.updated",
                actor=actor,
                subject_type="job",
                subject_id=job_id,
                payload={"changed_fields": sorted(set(changes) - {"updated_at"})},
            )
        return self._load_job(job_id)

    def transition_job(
        self,
        job_id: str,
        *,
        target: str,
        actor: str,
        note: str,
        restrict_to_assignee: bool = False,
    ) -> JobSummary | None:
        from .domain import JOB_TRANSITIONS

        with schedule_write_lock, self.engine.begin() as db:
            lock_schedule_job(db, job_id)
            current = (
                db.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            )
            if not current:
                return None
            if restrict_to_assignee and current["assigned_to"] != actor:
                return None
            if target not in JOB_TRANSITIONS[current["status"]]:
                raise ValueError(
                    f"Job cannot move from {current['status']} to {target}"
                )
            now = datetime.now(UTC)
            if target in {"completed", "cancelled"}:
                active_schedule = db.execute(
                    select(schedule_entries.c.id).where(
                        schedule_entries.c.job_id == job_id,
                        schedule_entries.c.status == "in_progress",
                    )
                ).first()
                if active_schedule:
                    raise ValueError(
                        "Finish the in-progress schedule entry before closing the job"
                    )
                scheduled_entries = (
                    db.execute(
                        select(
                            schedule_entries.c.id,
                            schedule_entries.c.version,
                        ).where(
                            schedule_entries.c.job_id == job_id,
                            schedule_entries.c.status == "scheduled",
                        )
                    )
                    .mappings()
                    .all()
                )
                for entry in scheduled_entries:
                    history_id = str(uuid4())
                    next_version = entry["version"] + 1
                    retired = db.execute(
                        update(schedule_entries)
                        .where(
                            schedule_entries.c.id == entry["id"],
                            schedule_entries.c.status == "scheduled",
                            schedule_entries.c.version == entry["version"],
                        )
                        .values(
                            status="cancelled",
                            version=next_version,
                            updated_at=now,
                        )
                    )
                    if retired.rowcount != 1:
                        raise ValueError(
                            "Schedule changed concurrently; reload before closing job"
                        )
                    db.execute(
                        schedule_status_history.insert().values(
                            id=history_id,
                            schedule_entry_id=entry["id"],
                            from_status="scheduled",
                            to_status="cancelled",
                            note=(
                                f"Automatically retired when job moved to {target}. "
                                f"{note.strip()}"
                            ).strip(),
                            actor=actor,
                            occurred_at=now,
                        )
                    )
                    self._audit(
                        db,
                        event="schedule.status_changed",
                        actor=actor,
                        subject_type="schedule_entry",
                        subject_id=entry["id"],
                        payload={
                            "from": "scheduled",
                            "to": "cancelled",
                            "from_version": entry["version"],
                            "to_version": next_version,
                            "history_id": history_id,
                            "reason": "job_terminal",
                        },
                    )
            changed = db.execute(
                update(jobs)
                .where(jobs.c.id == job_id, jobs.c.status == current["status"])
                .values(status=target, updated_at=now)
            )
            if changed.rowcount != 1:
                raise ValueError("Job changed concurrently; reload before retrying")
            self._audit(
                db,
                event="job.status_changed",
                actor=actor,
                subject_type="job",
                subject_id=job_id,
                payload={
                    "from": current["status"],
                    "to": target,
                    "note": note.strip(),
                },
            )
        return self._load_job(job_id)

    def list_job_audit(
        self, job_id: str, *, actor: str = "", role: Role | None = None
    ) -> list[dict[str, Any]] | None:
        with self.engine.connect() as db:
            exists = select(jobs.c.id).where(jobs.c.id == job_id)
            if role is Role.FIELD:
                exists = exists.where(jobs.c.assigned_to == actor)
            if not db.execute(exists).first():
                return None
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "job",
                        audit_events.c.subject_id == job_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
