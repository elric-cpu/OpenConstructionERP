import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from fastapi import HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.security import Principal
from app.modules.platform.auth_schemas import MfaEnrollment, MfaVerifyRequest, TokenResponse
from app.modules.platform.auth_service import complete_login, hash_secret
from app.modules.platform.models import Membership, User

MFA_AUDIENCE = "benson-erp-mfa"


def create_challenge(user_id: uuid.UUID, tenant_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "tenant": str(tenant_id),
            "email": email,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "aud": MFA_AUDIENCE,
            "iss": "benson-erp",
            "purpose": "mfa_login",
        },
        settings.secret_key,
        algorithm="HS256",
    )


async def verify_login(
    session: AsyncSession,
    request: Request,
    data: MfaVerifyRequest,
) -> tuple[TokenResponse, str]:
    user_id, tenant_id, email = _decode_challenge(data.challenge_token)
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    membership = await session.scalar(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    )
    if user is None or membership is None or not user.mfa_enabled:
        raise _invalid_code()
    if not _consume_code(user, data.code):
        raise _invalid_code()
    return await complete_login(
        session, request, tenant_id, user, membership, data.device_name, email
    )


async def begin_enrollment(
    session: AsyncSession, principal: Principal, issuer: str = "Benson Construction ERP"
) -> MfaEnrollment:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    secret = pyotp.random_base32()
    recovery_codes = [_recovery_code() for _ in range(10)]
    user.mfa_pending_secret_encrypted = encrypt_secret(secret)
    user.mfa_pending_recovery_code_hashes = [hash_secret(code) for code in recovery_codes]
    await session.commit()
    return MfaEnrollment(
        secret=secret,
        provisioning_uri=pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer),
        recovery_codes=recovery_codes,
    )


async def confirm_enrollment(session: AsyncSession, principal: Principal, code: str) -> None:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    if user is None or user.mfa_pending_secret_encrypted is None:
        raise HTTPException(status_code=409, detail="MFA enrollment has not started")
    secret = decrypt_secret(user.mfa_pending_secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise _invalid_code()
    user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
    user.mfa_pending_secret_encrypted = None
    user.mfa_recovery_code_hashes = list(user.mfa_pending_recovery_code_hashes)
    user.mfa_pending_recovery_code_hashes = []
    user.mfa_enabled = True
    await session.commit()


def _consume_code(user: User, code: str) -> bool:
    normalized = code.strip().upper()
    if user.mfa_secret_encrypted and normalized.isdigit():
        secret = decrypt_secret(user.mfa_secret_encrypted)
        return bool(pyotp.TOTP(secret).verify(normalized, valid_window=1))
    code_hash = hash_secret(normalized)
    if code_hash not in user.mfa_recovery_code_hashes:
        return False
    user.mfa_recovery_code_hashes = [
        stored for stored in user.mfa_recovery_code_hashes if stored != code_hash
    ]
    return True


def _decode_challenge(token: str) -> tuple[uuid.UUID, uuid.UUID, str]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            audience=MFA_AUDIENCE,
            issuer="benson-erp",
        )
        if payload.get("purpose") != "mfa_login":
            raise ValueError("Wrong challenge purpose")
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["tenant"]), payload["email"]
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise _invalid_code() from exc


def _recovery_code() -> str:
    value = secrets.token_hex(4).upper()
    return f"{value[:4]}-{value[4:]}"


def _invalid_code() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")
