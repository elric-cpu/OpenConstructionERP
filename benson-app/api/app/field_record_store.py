import json
from datetime import UTC, date, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update

from .domain import Role
from .field_record_domain import (
    FieldPhotoSummary,
    FieldReportContent,
    FieldReportCreate,
    FieldReportSummary,
)
from .store_base import StoreBase
from .storage_schema import (
    audit_events,
    field_report_corrections,
    field_report_photos,
    field_reports,
    jobs,
)

field_report_write_lock = RLock()
MAX_REPORT_PHOTOS = 20
MAX_REPORT_PHOTO_BYTES = 75_000_000


class FieldReportStaleWrite(ValueError):
    pass


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _content_values(content: FieldReportContent) -> dict[str, Any]:
    values = content.model_dump(exclude={"job_id", "service_date", "expected_version"})
    values["safety_observations"] = json.dumps(values["safety_observations"])
    return values


class FieldRecordStoreMixin(StoreBase):
    def list_field_reports(
        self,
        *,
        actor: str,
        role: Role,
        job_id: str | None,
        service_date: date | None,
        limit: int,
        offset: int,
    ) -> list[FieldReportSummary]:
        statement = self._field_summary_query()
        if role is Role.FIELD:
            statement = statement.where(jobs.c.assigned_to == actor)
        if job_id:
            statement = statement.where(field_reports.c.job_id == job_id)
        if service_date:
            statement = statement.where(field_reports.c.service_date == service_date)
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    statement.order_by(
                        field_reports.c.service_date.desc(),
                        field_reports.c.revision.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [self._field_summary(row) for row in rows]

    def get_field_report(
        self, report_id: str, *, actor: str, role: Role
    ) -> FieldReportSummary | None:
        statement = self._field_summary_query().where(field_reports.c.id == report_id)
        if role is Role.FIELD:
            statement = statement.where(jobs.c.assigned_to == actor)
        with self.engine.connect() as db:
            row = db.execute(statement).mappings().first()
        return self._field_summary(row) if row else None

    def create_field_report(
        self, report: FieldReportCreate, *, actor: str, role: Role
    ) -> FieldReportSummary | None:
        report_id = str(uuid4())
        now = datetime.now(UTC)
        with field_report_write_lock, self.engine.begin() as db:
            job = (
                db.execute(select(jobs).where(jobs.c.id == str(report.job_id)))
                .mappings()
                .first()
            )
            if not job or (role is Role.FIELD and job["assigned_to"] != actor):
                return None
            if job["status"] not in {"planned", "active"}:
                raise ValueError("Field reports require a planned or active job")
            latest = db.execute(
                select(func.max(field_reports.c.revision)).where(
                    field_reports.c.job_id == str(report.job_id),
                    field_reports.c.service_date == report.service_date,
                )
            ).scalar_one()
            if latest is not None:
                raise ValueError("A field report already exists for this job and date")
            db.execute(
                field_reports.insert().values(
                    id=report_id,
                    job_id=str(report.job_id),
                    service_date=report.service_date,
                    revision=1,
                    previous_revision_id=None,
                    status="draft",
                    version=1,
                    **_content_values(report),
                    created_by=actor,
                    submitted_by=None,
                    submitted_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._audit_field(
                db, report_id, "field_report.created", actor, {"version": 1}
            )
        return self.get_field_report(report_id, actor=actor, role=role)

    def update_field_report(
        self,
        report_id: str,
        content: FieldReportContent,
        *,
        expected_version: int,
        actor: str,
        role: Role,
    ) -> FieldReportSummary | None:
        with field_report_write_lock, self.engine.begin() as db:
            current = self._scoped_row(db, report_id, actor=actor, role=role)
            if not current:
                return None
            if current["status"] != "draft":
                raise ValueError("Submitted field report revisions are immutable")
            changed = db.execute(
                update(field_reports)
                .where(
                    field_reports.c.id == report_id,
                    field_reports.c.status == "draft",
                    field_reports.c.version == expected_version,
                )
                .values(
                    **_content_values(content),
                    version=expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise FieldReportStaleWrite(
                    "Field report changed; reload before retrying"
                )
            self._audit_field(
                db,
                report_id,
                "field_report.updated",
                actor,
                {"from_version": expected_version, "to_version": expected_version + 1},
            )
        return self.get_field_report(report_id, actor=actor, role=role)

    def submit_field_report(
        self, report_id: str, *, expected_version: int, actor: str, role: Role
    ) -> FieldReportSummary | None:
        with field_report_write_lock, self.engine.begin() as db:
            current = self._scoped_row(db, report_id, actor=actor, role=role)
            if not current:
                return None
            if current["status"] != "draft":
                raise ValueError("Only draft field reports may be submitted")
            if not str(current["completed_work"]).strip():
                raise ValueError("Completed work is required before submission")
            target = "corrected" if current["previous_revision_id"] else "submitted"
            now = datetime.now(UTC)
            changed = db.execute(
                update(field_reports)
                .where(
                    field_reports.c.id == report_id,
                    field_reports.c.status == "draft",
                    field_reports.c.version == expected_version,
                )
                .values(
                    status=target,
                    version=expected_version + 1,
                    submitted_by=actor,
                    submitted_at=now,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise FieldReportStaleWrite(
                    "Field report changed; reload before retrying"
                )
            previous_id = current["previous_revision_id"]
            if previous_id:
                db.execute(
                    update(field_reports)
                    .where(
                        field_reports.c.id == previous_id,
                        field_reports.c.status == "correction_required",
                    )
                    .values(status="superseded", updated_at=now)
                )
            self._audit_field(
                db,
                report_id,
                "field_report.submitted",
                actor,
                {"status": target, "revision": current["revision"]},
            )
        return self.get_field_report(report_id, actor=actor, role=role)

    def request_field_report_correction(
        self, report_id: str, *, expected_version: int, reason: str, actor: str
    ) -> FieldReportSummary | None:
        with field_report_write_lock, self.engine.begin() as db:
            current = (
                db.execute(select(field_reports).where(field_reports.c.id == report_id))
                .mappings()
                .first()
            )
            if not current:
                return None
            if current["status"] not in {"submitted", "corrected"}:
                raise ValueError("Only submitted reports may require correction")
            changed = db.execute(
                update(field_reports)
                .where(
                    field_reports.c.id == report_id,
                    field_reports.c.status == current["status"],
                    field_reports.c.version == expected_version,
                )
                .values(
                    status="correction_required",
                    version=expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise FieldReportStaleWrite(
                    "Field report changed; reload before retrying"
                )
            db.execute(
                field_report_corrections.insert().values(
                    id=str(uuid4()),
                    field_report_id=report_id,
                    reason=reason.strip(),
                    requested_by=actor,
                    requested_at=datetime.now(UTC),
                )
            )
            self._audit_field(
                db,
                report_id,
                "field_report.correction_required",
                actor,
                {"reason": reason.strip()},
            )
        return self.get_field_report(report_id, actor=actor, role=Role.OWNER)

    def create_field_report_revision(
        self, report_id: str, *, expected_version: int, actor: str, role: Role
    ) -> FieldReportSummary | None:
        revision_id = str(uuid4())
        with field_report_write_lock, self.engine.begin() as db:
            current = self._scoped_row(db, report_id, actor=actor, role=role)
            if not current:
                return None
            if current["status"] != "correction_required":
                raise ValueError("A correction request is required before revising")
            if current["version"] != expected_version:
                raise FieldReportStaleWrite(
                    "Field report changed; reload before retrying"
                )
            existing = db.execute(
                select(field_reports.c.id).where(
                    field_reports.c.previous_revision_id == report_id
                )
            ).first()
            if existing:
                raise ValueError("A correction revision already exists")
            now = datetime.now(UTC)
            values = {
                name: current[name]
                for name in (
                    "workforce_total",
                    "workforce_hours",
                    "weather",
                    "completed_work",
                    "materials",
                    "equipment",
                    "delays",
                    "issues",
                    "safety_observations",
                )
            }
            db.execute(
                field_reports.insert().values(
                    id=revision_id,
                    job_id=current["job_id"],
                    service_date=current["service_date"],
                    revision=current["revision"] + 1,
                    previous_revision_id=report_id,
                    status="draft",
                    version=1,
                    **values,
                    created_by=actor,
                    submitted_by=None,
                    submitted_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._audit_field(
                db,
                revision_id,
                "field_report.revision_created",
                actor,
                {"previous_revision_id": report_id},
            )
        return self.get_field_report(revision_id, actor=actor, role=role)

    def add_field_photo(
        self,
        report_id: str,
        *,
        stage: str,
        original_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        actor: str,
        role: Role,
    ) -> FieldPhotoSummary | None:
        photo_id = str(uuid4())
        with field_report_write_lock, self.engine.begin() as db:
            current = self._scoped_row(db, report_id, actor=actor, role=role)
            if not current:
                return None
            if current["status"] != "draft":
                raise ValueError("Photos cannot be added to submitted revisions")
            totals = db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(field_report_photos.c.size_bytes), 0),
                ).where(field_report_photos.c.field_report_id == report_id)
            ).one()
            if (
                totals[0] >= MAX_REPORT_PHOTOS
                or totals[1] + size_bytes > MAX_REPORT_PHOTO_BYTES
            ):
                raise ValueError("Field report photo quota exceeded")
            now = datetime.now(UTC)
            db.execute(
                field_report_photos.insert().values(
                    id=photo_id,
                    field_report_id=report_id,
                    stage=stage,
                    original_name=original_name,
                    storage_key=storage_key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    uploaded_by=actor,
                    created_at=now,
                )
            )
            self._audit_field(
                db,
                report_id,
                "field_report.photo_added",
                actor,
                {"photo_id": photo_id, "stage": stage, "sha256": sha256},
            )
        return FieldPhotoSummary(
            id=photo_id,
            field_report_id=report_id,
            stage=stage,
            original_name=original_name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            uploaded_by=actor,
            created_at=now,
        )

    def list_field_photos(
        self, report_id: str, *, actor: str, role: Role
    ) -> list[FieldPhotoSummary] | None:
        with self.engine.connect() as db:
            if not self._scoped_row(db, report_id, actor=actor, role=role):
                return None
            rows = (
                db.execute(
                    select(field_report_photos)
                    .where(field_report_photos.c.field_report_id == report_id)
                    .order_by(field_report_photos.c.created_at)
                )
                .mappings()
                .all()
            )
        return [FieldPhotoSummary.model_validate(dict(row)) for row in rows]

    def get_field_photo(
        self, report_id: str, photo_id: str, *, actor: str, role: Role
    ) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            if not self._scoped_row(db, report_id, actor=actor, role=role):
                return None
            row = (
                db.execute(
                    select(field_report_photos).where(
                        field_report_photos.c.id == photo_id,
                        field_report_photos.c.field_report_id == report_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def list_field_report_audit(
        self, report_id: str, *, actor: str, role: Role
    ) -> list[dict[str, Any]] | None:
        with self.engine.connect() as db:
            if not self._scoped_row(db, report_id, actor=actor, role=role):
                return None
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "field_report",
                        audit_events.c.subject_id == report_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    @staticmethod
    def _scoped_row(db: Any, report_id: str, *, actor: str, role: Role) -> Any:
        statement = (
            select(field_reports)
            .join(jobs, jobs.c.id == field_reports.c.job_id)
            .where(field_reports.c.id == report_id)
        )
        if role is Role.FIELD:
            statement = statement.where(jobs.c.assigned_to == actor)
        return db.execute(statement).mappings().first()

    @staticmethod
    def _field_summary_query() -> Any:
        return select(
            field_reports,
            jobs.c.number.label("job_number"),
            jobs.c.title.label("job_title"),
        ).join(jobs, jobs.c.id == field_reports.c.job_id)

    @staticmethod
    def _field_summary(row: Any) -> FieldReportSummary:
        payload = dict(row)
        payload["safety_observations"] = json.loads(payload["safety_observations"])
        for field in ("submitted_at", "created_at", "updated_at"):
            payload[field] = _utc(payload[field])
        return FieldReportSummary.model_validate(payload)

    def _audit_field(
        self, db: Any, report_id: str, event: str, actor: str, payload: dict[str, Any]
    ) -> None:
        self._audit(
            db,
            event=event,
            actor=actor,
            subject_type="field_report",
            subject_id=report_id,
            payload=payload,
        )
