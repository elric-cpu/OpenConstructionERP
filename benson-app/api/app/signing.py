import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import HTTPException, status


def signature_for(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def employee_invite_token(secret: str, invite_id: str) -> str:
    signature = hmac.new(
        secret.encode(), invite_id.encode(), hashlib.sha256
    ).hexdigest()
    return f"{invite_id}.{signature}"


def verify_website_signature(
    *,
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    max_age_seconds: int,
) -> None:
    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signed website request required",
        )
    try:
        sent_at = datetime.fromtimestamp(int(timestamp), UTC)
    except (ValueError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid website timestamp"
        ) from error
    age = abs((datetime.now(UTC) - sent_at).total_seconds())
    if age > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired website request"
        )
    expected = signature_for(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid website signature"
        )
