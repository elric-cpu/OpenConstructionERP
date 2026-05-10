# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for ``_detect_language_mismatch`` (#229).

The helper compares the project region's language with the bound CWICR
catalogue's language so the UI can surface a "wrong catalogue" warning.
This file isolates the helper from the HTTP layer — the integration
test in ``tests/integration/test_match_catalog_binding.py`` covers the
full /vector/v3-status endpoint round trip.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.modules.costs.router import _detect_language_mismatch


def _register_models() -> None:
    import app.core.audit  # noqa: F401
    import app.modules.costs.models  # noqa: F401
    import app.modules.projects.models  # noqa: F401
    import app.modules.users.models  # noqa: F401


async def _make_project(
    s: AsyncSession,
    *,
    region: str,
) -> uuid.UUID:
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    user = User(
        id=uuid.uuid4(),
        email=f"lm-{uuid.uuid4().hex[:6]}@test.io",
        hashed_password="x" * 60,
        full_name="Lang Mismatch Test",
        role="estimator",
        locale="en",
        is_active=True,
        metadata_={},
    )
    s.add(user)
    await s.flush()

    pid = uuid.uuid4()
    s.add(
        Project(
            id=pid,
            name="t",
            region=region,
            status="active",
            owner_id=user.id,
        )
    )
    await s.commit()
    return pid


async def _bind(
    s: AsyncSession,
    project_id: uuid.UUID,
    catalogue_id: str | None,
) -> None:
    from app.modules.projects.models import MatchProjectSettings

    row = MatchProjectSettings(
        project_id=project_id,
        cost_database_id=catalogue_id,
    )
    s.add(row)
    await s.commit()


async def _run_with_session(callback):
    """Build a fresh DB session per test — async fixtures need plumbing."""
    tmp_db = Path(tempfile.mkdtemp()) / "lang_mismatch.db"
    url = f"sqlite+aiosqlite:///{tmp_db.as_posix()}"
    engine = create_async_engine(url, future=True)
    _register_models()
    from app.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            return await callback(s)
    finally:
        await engine.dispose()


def test_unknown_when_project_missing() -> None:
    async def go(s: AsyncSession) -> dict:
        return await _detect_language_mismatch(s, uuid.uuid4())

    out = asyncio.run(_run_with_session(go))
    assert out["status"] == "unknown"


def test_unbound_when_no_catalogue() -> None:
    async def go(s: AsyncSession) -> dict:
        pid = await _make_project(s, region="USA_NEWYORK")
        # Settings row absent ⇒ unbound
        return await _detect_language_mismatch(s, pid)

    out = asyncio.run(_run_with_session(go))
    assert out["status"] == "unbound"
    assert out["project_region"] == "USA_NEWYORK"
    assert out["project_language"] == "en"


def test_ok_when_languages_match() -> None:
    async def go(s: AsyncSession) -> dict:
        pid = await _make_project(s, region="USA_NEWYORK")
        await _bind(s, pid, "USA_USD")  # also "en"
        return await _detect_language_mismatch(s, pid)

    out = asyncio.run(_run_with_session(go))
    assert out["status"] == "ok"
    assert out["project_language"] == "en"
    assert out["bound_language"] == "en"


def test_mismatch_us_project_with_russian_catalogue() -> None:
    """The motivating bug: US project auto-bound to RU_MOSCOW because the
    Russian catalogue had the most rows globally (auto_bind_dominant_catalogue
    pre-2.9.34 picked by row count). The /match-elements UI must now flag
    this as a mismatch so the user can re-bind."""

    async def go(s: AsyncSession) -> dict:
        pid = await _make_project(s, region="USA_NEWYORK")
        await _bind(s, pid, "RU_MOSCOW")
        return await _detect_language_mismatch(s, pid)

    out = asyncio.run(_run_with_session(go))
    assert out["status"] == "mismatch"
    assert out["project_language"] == "en"
    assert out["bound_language"] == "ru"
    assert out["project_region"] == "USA_NEWYORK"
    assert out["bound_catalogue"] == "RU_MOSCOW"


def test_mismatch_de_project_with_french_catalogue() -> None:
    async def go(s: AsyncSession) -> dict:
        pid = await _make_project(s, region="DE_BERLIN")
        await _bind(s, pid, "FR_PARIS")
        return await _detect_language_mismatch(s, pid)

    out = asyncio.run(_run_with_session(go))
    assert out["status"] == "mismatch"
    assert out["project_language"] == "de"
    assert out["bound_language"] == "fr"
