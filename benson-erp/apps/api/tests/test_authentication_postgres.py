import os
import uuid

import pyotp
import pytest
from app.core.database import SessionFactory
from app.main import app
from app.modules.platform.auth_service import password_hash
from app.modules.platform.models import (
    LoginEvent,
    LoginSession,
    Membership,
    Organization,
    User,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1", reason="PostgreSQL integration tests disabled"
    ),
]


async def test_login_refresh_rotation_and_logout_revocation() -> None:
    organization, user, password = await _seed_identity()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://benson-ai") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "organization": organization.slug,
                "email": user.email,
                "password": password,
                "device_name": "Integration test browser",
            },
        )
        assert login.status_code == 200, login.text
        login_body = login.json()
        first_refresh_cookie = client.cookies["erp_refresh"]
        access_token = login_body["access_token"]

        authorized = await client.post(
            "/api/v1/leads",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "contact_name": "Authenticated User",
                "source": "TEST",
                "summary": "Authentication verification",
            },
        )
        assert authorized.status_code == 201, authorized.text

        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"csrf_token": login_body["csrf_token"]}
        )
        assert refreshed.status_code == 200, refreshed.text
        assert client.cookies["erp_refresh"] != first_refresh_cookie

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            cookies={"erp_refresh": first_refresh_cookie},
        ) as replay_client:
            replay = await replay_client.post(
                "/api/v1/auth/refresh", json={"csrf_token": login_body["csrf_token"]}
            )
        assert replay.status_code == 401

        current_access = refreshed.json()["access_token"]
        logout = await client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {current_access}"}
        )
        assert logout.status_code == 204
        rejected = await client.post(
            "/api/v1/leads",
            headers={"Authorization": f"Bearer {current_access}"},
            json={
                "contact_name": "Revoked User",
                "source": "TEST",
                "summary": "This must not be created",
            },
        )
        assert rejected.status_code == 401

    await _cleanup_identity(organization, user)


async def test_mfa_enrollment_challenge_recovery_and_session_listing() -> None:
    organization, user, password = await _seed_identity()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://benson-ai") as client:
        login = await _login(client, organization, user, password)
        access_token = login["access_token"]
        enrollment_response = await client.post(
            "/api/v1/auth/mfa/enroll",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert enrollment_response.status_code == 200, enrollment_response.text
        enrollment = enrollment_response.json()
        confirm = await client.post(
            "/api/v1/auth/mfa/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"code": pyotp.TOTP(enrollment["secret"]).now()},
        )
        assert confirm.status_code == 204, confirm.text
        await client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
        )

        challenged = await _login(client, organization, user, password)
        assert challenged["mfa_required"] is True
        verified = await client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "challenge_token": challenged["mfa_challenge_token"],
                "code": pyotp.TOTP(enrollment["secret"]).now(),
                "device_name": "MFA integration browser",
            },
        )
        assert verified.status_code == 200, verified.text
        mfa_access = verified.json()["access_token"]
        sessions = await client.get(
            "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {mfa_access}"}
        )
        assert sessions.status_code == 200
        assert any(item["current"] for item in sessions.json())
        await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {mfa_access}"})

        recovery_challenge = await _login(client, organization, user, password)
        recovery_code = enrollment["recovery_codes"][0]
        recovered = await client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "challenge_token": recovery_challenge["mfa_challenge_token"],
                "code": recovery_code,
            },
        )
        assert recovered.status_code == 200, recovered.text
        await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {recovered.json()['access_token']}"},
        )
        replay_challenge = await _login(client, organization, user, password)
        replay = await client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "challenge_token": replay_challenge["mfa_challenge_token"],
                "code": recovery_code,
            },
        )
        assert replay.status_code == 401

    await _cleanup_identity(organization, user)


async def _login(
    client: AsyncClient, organization: Organization, user: User, password: str
) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "organization": organization.slug,
            "email": user.email,
            "password": password,
            "device_name": "Integration test browser",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _seed_identity() -> tuple[Organization, User, str]:
    suffix = uuid.uuid4().hex
    password = f"Correct-Horse-{suffix}"
    organization = Organization(name="Auth Test", slug=f"auth-test-{suffix}")
    user = User(
        email=f"auth+{suffix}@bensonhomesolutions.com",
        password_hash=password_hash.hash(password),
    )
    async with SessionFactory() as session:
        session.add_all((organization, user))
        await session.flush()
        session.add(
            Membership(
                tenant_id=organization.id,
                user_id=user.id,
                permissions=["leads.create"],
            )
        )
        await session.commit()
    return organization, user, password


async def _cleanup_identity(organization: Organization, user: User) -> None:
    async with SessionFactory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(organization.id)},
        )
        for model in (LoginEvent, LoginSession):
            await session.execute(delete(model).where(model.tenant_id == organization.id))
        await session.execute(
            delete(Membership).where(
                Membership.tenant_id == organization.id, Membership.user_id == user.id
            )
        )
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Organization).where(Organization.id == organization.id))
        await session.commit()
