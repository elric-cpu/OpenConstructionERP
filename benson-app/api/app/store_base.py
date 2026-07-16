import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.engine import Engine

from .domain import EmployeeTaskSummary
from .lead_rules import classify_spam, lead_source
from .storage_schema import audit_events, leads, metadata


class StoreBase:
    def __init__(self, database_url: str):
        connect_args = (
            {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        )
        self.engine: Engine = create_engine(
            database_url, pool_pre_ping=True, connect_args=connect_args
        )

    def initialize_schema(self) -> None:
        metadata.create_all(self.engine)
        existing = {
            column["name"] for column in inspect(self.engine).get_columns("leads")
        }
        source_added = "source" not in existing
        additions = {
            "source": "VARCHAR(200) NOT NULL DEFAULT 'Website'",
            "is_spam": "INTEGER NOT NULL DEFAULT 0",
            "spam_reason": "VARCHAR(500)",
            "deleted_at": "TIMESTAMP WITH TIME ZONE",
        }
        with self.engine.begin() as db:
            for name, definition in additions.items():
                if name not in existing:
                    db.execute(
                        text(f"ALTER TABLE leads ADD COLUMN {name} {definition}")
                    )
            if source_added:
                rows = db.execute(select(leads.c.id, leads.c.payload)).mappings()
                for row in rows:
                    payload = json.loads(row["payload"])
                    source = lead_source(payload)
                    is_spam, reason = classify_spam(payload)
                    db.execute(
                        update(leads)
                        .where(leads.c.id == row["id"])
                        .values(source=source, is_spam=int(is_spam), spam_reason=reason)
                    )
        employee_existing = {
            column["name"] for column in inspect(self.engine).get_columns("employees")
        }
        employee_additions = {
            "invite_delivery_email": "VARCHAR(320)",
            "workspace_account_status": (
                "VARCHAR(40) NOT NULL DEFAULT 'external_unlicensed_required'"
            ),
        }
        with self.engine.begin() as db:
            for name, definition in employee_additions.items():
                if name not in employee_existing:
                    db.execute(
                        text(f"ALTER TABLE employees ADD COLUMN {name} {definition}")
                    )

    def readiness_probe(self) -> None:
        with self.engine.connect() as db:
            db.execute(select(1)).scalar_one()

    def list_employee_tasks(self, employee_id: str) -> list[EmployeeTaskSummary]:
        raise NotImplementedError

    def _audit(
        self,
        db: Any,
        *,
        event: str,
        actor: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        db.execute(
            audit_events.insert().values(
                id=str(uuid4()),
                event=event,
                actor=actor,
                subject_type=subject_type,
                subject_id=subject_id,
                payload=json.dumps(payload, sort_keys=True),
                occurred_at=datetime.now(UTC),
            )
        )
