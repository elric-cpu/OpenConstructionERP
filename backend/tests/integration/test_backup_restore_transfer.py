"""Cross-machine transfer: export as one user, restore as another.

Regression for the restore that aborted on a second PC. The exporter's own
``users`` row travels in the backup with its password hash stripped, and its
email is already taken on the target machine, so re-inserting it failed the
NOT NULL password and the unique email and rolled the whole restore back with
a 500. Restore now skips the users table and repoints every ownership column to
the restoring user, so a backup taken on one machine lands cleanly under the
restoring account on another and the data is actually visible there.

These tests run the real ``restore_backup_data`` service against a
transaction-isolated PostgreSQL session.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.modules.backup.service import (
    RESTORE_SKIP_KEYS,
    _STRIP_FIELDS,
    build_scope_clause,
    get_backup_tables,
    restore_backup_data,
    serialize_row,
)
from tests._pg import transactional_session

MACHINE_A_USER = uuid.uuid4()
MACHINE_B_USER = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


async def _export_scope(session, owner_id):
    """Mimic build_backup: per-table scoped rows, serialized, sensitive fields stripped."""
    tables = get_backup_tables()
    by_key = {k: cls for k, _t, cls in tables}
    data: dict[str, list[dict]] = {}
    for key, _t, cls in tables:
        clause = build_scope_clause(by_key, key, str(owner_id))
        rows = [] if clause is None else (await session.execute(select(cls).where(clause))).scalars().all()
        data[key] = [{k: v for k, v in serialize_row(r).items() if k not in _STRIP_FIELDS} for r in rows]
    return data


@pytest_asyncio.fixture
async def session():
    """Two accounts on notionally different machines, each with its own password."""
    async with transactional_session() as s:
        from app.modules.users.models import User

        s.add(User(id=MACHINE_A_USER, email="a@pc.io", hashed_password="secret-a", full_name="A"))
        s.add(User(id=MACHINE_B_USER, email="b@pc.io", hashed_password="secret-b", full_name="B"))
        await s.flush()
        yield s


@pytest.mark.asyncio
async def test_backup_transfers_to_the_restoring_user(session):
    """Export A's project graph, then restore it as B on a clean second machine."""
    from app.modules.boq.models import BOQ, Position
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    # Machine A builds a project graph and exports it.
    session.add(Project(id=PROJECT_ID, name="Tower", owner_id=MACHINE_A_USER, currency="EUR"))
    await session.flush()
    boq = BOQ(project_id=PROJECT_ID, name="BOQ-A")
    session.add(boq)
    await session.flush()
    for i in range(3):
        session.add(Position(boq_id=boq.id, ordinal=f"{i:03d}", description=f"pos {i}", unit="m3"))
    await session.flush()

    data = await _export_scope(session, MACHINE_A_USER)
    # The backup carries the exporter's own user row, password stripped.
    assert data["users"], "export should include the exporter's own user row"
    assert "hashed_password" not in data["users"][0]
    assert len(data["positions"]) == 3

    # Simulate the second machine: a fresh session that has never loaded A's
    # objects or seen A's data or account.
    session.expunge_all()
    await session.execute(Position.__table__.delete())
    await session.execute(BOQ.__table__.delete())
    await session.execute(Project.__table__.delete())
    await session.execute(User.__table__.delete().where(User.id == MACHINE_A_USER))
    await session.flush()

    # User B restores the backup. This used to abort with a 500 on the users insert.
    imported, skipped, _warnings = await restore_backup_data(
        session,
        user_id=str(MACHINE_B_USER),
        manifest={"created_by": str(MACHINE_A_USER)},
        data=data,
        mode="replace",
    )

    # The project graph is back, now owned by the restoring user.
    proj = (await session.execute(select(Project).where(Project.id == PROJECT_ID))).scalar_one()
    assert str(proj.owner_id) == str(MACHINE_B_USER)
    assert (await session.execute(select(func.count()).select_from(Position))).scalar_one() == 3

    # The exporter's account was NOT re-created: the users table is left alone.
    assert "users" in RESTORE_SKIP_KEYS
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 1
    only_user = (await session.execute(select(User))).scalar_one()
    assert str(only_user.id) == str(MACHINE_B_USER)
    assert only_user.hashed_password == "secret-b", "the restoring account keeps its own password"

    # Nothing failed: users reports 0 imported (skipped table), the graph imported cleanly.
    assert imported["users"] == 0
    assert imported["projects"] == 1
    assert imported["positions"] == 3
    assert skipped["projects"] == 0


@pytest.mark.asyncio
async def test_restore_leaves_other_users_untouched_and_repoints_ownership(session):
    """Restoring as B must not delete or duplicate any other account's rows."""
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    # A owns a project; B owns nothing yet.
    session.add(Project(id=PROJECT_ID, name="Bridge", owner_id=MACHINE_A_USER, currency="EUR"))
    await session.flush()
    data = await _export_scope(session, MACHINE_A_USER)

    # Both accounts still exist here (same-instance restore, e.g. moving a project
    # between two users). Fresh session, remove only A's project so no PK clash.
    session.expunge_all()
    await session.execute(Project.__table__.delete())
    await session.flush()

    await restore_backup_data(
        session,
        user_id=str(MACHINE_B_USER),
        manifest={"created_by": str(MACHINE_A_USER)},
        data=data,
        mode="replace",
    )

    # Both users survive; the project is now B's.
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 2
    proj = (await session.execute(select(Project).where(Project.id == PROJECT_ID))).scalar_one()
    assert str(proj.owner_id) == str(MACHINE_B_USER)
