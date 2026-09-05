import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update

from .store_base import StoreBase
from .storage_schema import ai_proposals, ai_runs


class AiStoreMixin(StoreBase):
    def create_ai_run(
        self,
        *,
        skill_id: str,
        actor: str,
        role: str,
        status: str,
        prompt: str,
        summary: str,
        model: str,
        context: dict[str, Any],
        risk: str,
    ) -> tuple[str, str | None]:
        run_id = str(uuid4())
        proposal_id = str(uuid4()) if risk != "internal" else None
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            db.execute(
                ai_runs.insert().values(
                    id=run_id,
                    skill_id=skill_id,
                    actor=actor,
                    role=role,
                    status=status,
                    prompt=prompt,
                    summary=summary,
                    model=model,
                    context=json.dumps(context, sort_keys=True),
                    created_at=now,
                )
            )
            if proposal_id:
                db.execute(
                    ai_proposals.insert().values(
                        id=proposal_id,
                        run_id=run_id,
                        status="pending",
                        risk=risk,
                        action=json.dumps(
                            {"skill_id": skill_id, "summary": summary}, sort_keys=True
                        ),
                        created_at=now,
                    )
                )
            self._audit(
                db,
                event="ai.run_completed",
                actor=actor,
                subject_type="ai_run",
                subject_id=run_id,
                payload={
                    "skill_id": skill_id,
                    "risk": risk,
                    "proposal_id": proposal_id,
                },
            )
        return run_id, proposal_id

    def decide_proposal(
        self, proposal_id: str, *, approved: bool, actor: str, comment: str
    ) -> bool:
        with self.engine.begin() as db:
            existing = (
                db.execute(select(ai_proposals).where(ai_proposals.c.id == proposal_id))
                .mappings()
                .first()
            )
            if not existing or existing["status"] != "pending":
                return False
            result = db.execute(
                update(ai_proposals)
                .where(
                    ai_proposals.c.id == proposal_id, ai_proposals.c.status == "pending"
                )
                .values(
                    status="approved" if approved else "rejected",
                    decided_by=actor,
                    decision_comment=comment,
                    decided_at=datetime.now(UTC),
                )
            )
            if result.rowcount != 1:
                return False
            self._audit(
                db,
                event="ai.proposal_approved" if approved else "ai.proposal_rejected",
                actor=actor,
                subject_type="ai_proposal",
                subject_id=proposal_id,
                payload={"run_id": existing["run_id"], "comment": comment},
            )
        return True
