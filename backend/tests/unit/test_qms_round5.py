# DDC-CWICR-OE: DataDrivenConstruction / OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Round-5 QMS deepening tests — pure-helper + edge-case coverage.

These tests focus on the helpers / invariants that the R5 sweep added
to the QMS module:

* COPQ breakdown is a pure function — must compose ncr + rework +
  warranty + delay independently with Decimal precision.
* severity_to_rating_delta is a hash-stable map — no float drift, no
  side effects.
* signature dedup: a given (signer_user_id, role) pair cannot be added
  twice to the same inspection.
* ITP plan activation must reject empty plans (no items).
* Calibration valid_until must be strictly after calibration_date.

The hardened HTTP-layer tests live in
``tests/modules/test_qms_security.py``. This file is unit-only and runs
in milliseconds.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.modules.qms.models import (
    QMSNCR,
    ITPItem,
    ITPPlan,
    ITPTemplate,
    QMSAudit,
    QMSAuditFinding,
    QMSCalibration,
    QMSInspection,
    QMSInspectionSignature,
    QMSNCRAction,
    QMSPunchItem,
)
from app.modules.qms.schemas import (
    CalibrationCreate,
    InspectionCreate,
    InspectionSignatureCreate,
    ITPItemCreate,
    ITPPlanCreate,
)
from app.modules.qms.service import (
    QMSService,
    compute_copq_breakdown,
    severity_to_rating_delta,
)

_QMS_TABLES = [
    ITPPlan.__table__,
    ITPItem.__table__,
    ITPTemplate.__table__,
    QMSInspection.__table__,
    QMSInspectionSignature.__table__,
    QMSNCR.__table__,
    QMSNCRAction.__table__,
    QMSPunchItem.__table__,
    QMSAudit.__table__,
    QMSAuditFinding.__table__,
    QMSCalibration.__table__,
]


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_QMS_TABLES)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
        await sess.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def svc(session: AsyncSession) -> QMSService:
    return QMSService(session)


# ── Pure-helper invariants ──────────────────────────────────────────────


def test_severity_to_rating_delta_known_values() -> None:
    """‌⁠‍Map is hash-stable across releases."""
    assert severity_to_rating_delta("critical") == -3
    assert severity_to_rating_delta("major") == -2
    assert severity_to_rating_delta("minor") == -1
    assert severity_to_rating_delta("observation") == 0
    assert severity_to_rating_delta("unknown") == 0


def test_compute_copq_breakdown_decimal_precision() -> None:
    """‌⁠‍COPQ composes ncr + rework + warranty + delay with Decimal precision.

    Floats would drift past the 13th significant digit; Decimal does not.
    """
    result = compute_copq_breakdown(
        ncr_cost=Decimal("199.99"),
        open_punch_count=10,
        rework_cost_per_punch=Decimal("250.00"),
        warranty_cost=Decimal("0.01"),
        delay_penalty_cost=Decimal("1000.00"),
    )
    # 199.99 + 10*250.00 + 0.01 + 1000.00 = 3700.00
    assert result["ncr_cost"] == Decimal("199.99")
    assert result["rework_cost"] == Decimal("2500.00")
    assert result["warranty_cost"] == Decimal("0.01")
    assert result["delay_penalty_cost"] == Decimal("1000.00")
    assert result["copq_total"] == Decimal("3700.00")


def test_compute_copq_breakdown_with_zero_punch() -> None:
    """‌⁠‍No open punch -> rework = 0; copq = ncr + warranty + delay."""
    result = compute_copq_breakdown(
        ncr_cost=Decimal("500.00"),
        open_punch_count=0,
        rework_cost_per_punch=Decimal("250.00"),
    )
    assert result["rework_cost"] == Decimal("0")
    assert result["copq_total"] == Decimal("500.00")


# ── Inspection signature dedup (R5 add) ─────────────────────────────────


@pytest.mark.asyncio
async def test_signature_dedup_same_user_same_role(svc: QMSService) -> None:
    """‌⁠‍A (user, role) pair must not double-sign the same inspection."""
    project_id = uuid.uuid4()
    plan = await svc.create_itp_plan(
        ITPPlanCreate(project_id=project_id, name="dedup", work_type="t"),
    )
    item = await svc.add_itp_item(
        plan.id,
        ITPItemCreate(sequence=1, control_point_name="cp1"),
    )
    from datetime import datetime
    inspection = await svc.schedule_inspection(
        InspectionCreate(
            project_id=project_id,
            itp_item_id=item.id,
            scheduled_at=datetime(2026, 1, 1, 12, 0),
        ),
    )
    signer = uuid.uuid4()
    await svc.add_signature(
        inspection.id,
        InspectionSignatureCreate(signer_user_id=signer, signer_role="GC"),
    )
    with pytest.raises(ValueError, match="already signed"):
        await svc.add_signature(
            inspection.id,
            InspectionSignatureCreate(signer_user_id=signer, signer_role="GC"),
        )


@pytest.mark.asyncio
async def test_signature_dedup_allows_two_roles_one_user(
    svc: QMSService,
) -> None:
    """‌⁠‍The same user CAN sign in two different roles (multi-hat people)."""
    project_id = uuid.uuid4()
    plan = await svc.create_itp_plan(
        ITPPlanCreate(project_id=project_id, name="dedup2", work_type="t"),
    )
    item = await svc.add_itp_item(
        plan.id,
        ITPItemCreate(sequence=1, control_point_name="cp1"),
    )
    from datetime import datetime
    inspection = await svc.schedule_inspection(
        InspectionCreate(
            project_id=project_id,
            itp_item_id=item.id,
            scheduled_at=datetime(2026, 1, 1, 12, 0),
        ),
    )
    signer = uuid.uuid4()
    await svc.add_signature(
        inspection.id,
        InspectionSignatureCreate(signer_user_id=signer, signer_role="GC"),
    )
    # Same person, different role — allowed.
    sig2 = await svc.add_signature(
        inspection.id,
        InspectionSignatureCreate(signer_user_id=signer, signer_role="designer"),
    )
    assert sig2.signer_user_id == signer
    assert sig2.signer_role == "designer"


# ── ITP plan activation invariants ──────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_empty_itp_plan_rejected(svc: QMSService) -> None:
    """‌⁠‍A draft plan with no items cannot be activated."""
    project_id = uuid.uuid4()
    plan = await svc.create_itp_plan(
        ITPPlanCreate(project_id=project_id, name="empty", work_type="t"),
    )
    with pytest.raises(ValueError, match="no items"):
        await svc.activate_itp_plan(plan.id)


# ── Calibration date validity ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_calibration_valid_until_must_be_after_cal_date(
    svc: QMSService,
) -> None:
    """‌⁠‍valid_until must be strictly after calibration_date."""
    with pytest.raises(ValueError, match="valid_until must be after"):
        await svc.create_calibration(
            CalibrationCreate(
                project_id=uuid.uuid4(),
                instrument_id="i-1",
                instrument_name="Wrench",
                instrument_type="torque",
                calibration_date=date(2026, 6, 1),
                valid_until=date(2026, 6, 1),  # same day -> reject
            ),
        )
