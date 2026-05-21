"""‌⁠‍Smart Views baseline tests — first coverage for the v4.2.0 module.

Covers the three smoke paths the module must never regress on:

* ``test_create_and_list_view``    — author can create a user-scoped
                                     view and list it back.
* ``test_share_token_round_trip``  — a freshly-issued share token
                                     resolves the same view via the
                                     unauthenticated ``resolve_share_token``
                                     path, then 404s after revoke.
* ``test_share_token_signature_mismatch``
                                   — a token signed with the *wrong*
                                     JWT secret (simulates "token issued
                                     under a previous deployment") is
                                     rejected with 404 — never a 500
                                     and never leaks via 401.

Per ``feedback_test_isolation.md`` we use an isolated temp SQLite —
never ``backend/openestimate.db``.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from itsdangerous import URLSafeSerializer
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.modules.smart_views.schemas import (
    SmartViewCreate,
    SmartViewRule,
    SmartViewSelector,
)
from app.modules.smart_views.service import SmartViewService

OWNER_ID = uuid.uuid4()


def _register_models() -> None:
    # Order matters — SmartView FK targets users; the BIM models are
    # imported so the federation visibility join works under the
    # repository's federation-aware list query.
    import app.modules.bim_hub.models  # noqa: F401
    import app.modules.projects.models  # noqa: F401
    import app.modules.smart_views.models  # noqa: F401
    import app.modules.users.models  # noqa: F401


@pytest_asyncio.fixture
async def session():
    """Per-test isolated SQLite + a seeded owner user."""
    tmp_db = Path(tempfile.mkdtemp()) / "smart_views.db"
    url = f"sqlite+aiosqlite:///{tmp_db.as_posix()}"
    engine = create_async_engine(url, future=True)
    _register_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        from app.modules.users.models import User

        s.add(
            User(
                id=OWNER_ID,
                email=f"sv-{uuid.uuid4().hex[:6]}@test.io",
                hashed_password="x",
                full_name="SV Owner",
            )
        )
        await s.commit()
        yield s
    await engine.dispose()
    try:
        tmp_db.unlink(missing_ok=True)
        tmp_db.parent.rmdir()
    except OSError:
        pass


def _make_payload(name: str = "My Walls") -> SmartViewCreate:
    """A minimal user-scoped create payload — one selector, one action."""
    return SmartViewCreate(
        scope_type="user",
        scope_id=OWNER_ID,
        name=name,
        rules=[
            SmartViewRule(
                id="rule-1",
                selector=SmartViewSelector(ifc_class="IfcWall"),
                action="show",
            ),
        ],
    )


# ── create + list ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_view(session):
    """A user-scoped view round-trips through create → list."""
    service = SmartViewService(session)
    created = await service.create_view(_make_payload(), user_id=OWNER_ID)
    assert created.id is not None
    assert created.name == "My Walls"
    assert created.scope_type == "user"
    assert created.created_by == OWNER_ID

    listed = await service.list_views(user_id=OWNER_ID)
    assert len(listed) == 1
    assert listed[0].id == created.id


# ── share token round-trip ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_share_token_round_trip(session):
    """Issued token resolves; revoked token 404s; rotation invalidates old."""
    service = SmartViewService(session)
    view = await service.create_view(_make_payload(), user_id=OWNER_ID)

    info = await service.create_share_token(view.id, user_id=OWNER_ID)
    assert info.view_id == view.id
    assert info.share_token  # non-empty signed string
    assert info.url.endswith(info.share_token)

    # Valid token → view resolves (unauthenticated path).
    resolved = await service.resolve_share_token(info.share_token)
    assert resolved.id == view.id
    # ``share_token`` redaction: the unauthenticated path MUST NOT leak
    # the token back through the response payload.
    assert resolved.share_token is None

    # Rotate (re-share) — old token must stop working immediately.
    info2 = await service.create_share_token(view.id, user_id=OWNER_ID)
    assert info2.share_token != info.share_token
    with pytest.raises(HTTPException) as exc:
        await service.resolve_share_token(info.share_token)
    assert exc.value.status_code == 404

    # Revoke — even the freshly-issued token must stop working.
    await service.revoke_share_token(view.id, user_id=OWNER_ID)
    with pytest.raises(HTTPException) as exc2:
        await service.resolve_share_token(info2.share_token)
    assert exc2.value.status_code == 404


@pytest.mark.asyncio
async def test_share_token_signature_mismatch(session):
    """A token signed under a *different* JWT secret must 404, not 500.

    Simulates the "token issued under a previous deployment with a
    different ``JWT_SECRET``" scenario — and the related stale-token
    case where the wire token survived a secret rotation. Either way,
    the signer rejects the signature; we must surface a clean 404 and
    never leak existence via a 401.
    """
    service = SmartViewService(session)
    view = await service.create_view(_make_payload(), user_id=OWNER_ID)

    # Forge a token signed with a foreign secret but the right payload
    # shape — emulates an attacker (or a rotated install) replaying a
    # plausible token. Bad signature → 404.
    foreign_signer = URLSafeSerializer("not-the-real-secret", salt="oe.smart_views.share.v1")
    forged = foreign_signer.dumps({"v": str(view.id), "n": "deadbeef"})
    with pytest.raises(HTTPException) as exc:
        await service.resolve_share_token(forged)
    assert exc.value.status_code == 404

    # Pathological input — empty / oversized — also resolves to 404,
    # not a 500 from the signer doing real work.
    with pytest.raises(HTTPException) as exc_empty:
        await service.resolve_share_token("")
    assert exc_empty.value.status_code == 404

    with pytest.raises(HTTPException) as exc_huge:
        await service.resolve_share_token("a" * 5000)
    assert exc_huge.value.status_code == 404
