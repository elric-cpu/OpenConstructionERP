from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth import (
    Principal,
    require_owner,
    require_staff,
)
from app.config import Settings
from app.domain import Role


from tests.support import (
    production_settings,
)


def test_production_google_auth_and_owner_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = production_settings(
        owner_emails="owner@bensonhomesolutions.com",
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "owner@bensonhomesolutions.com",
                "email_verified": True,
                "hd": "bensonhomesolutions.com",
                "sub": "google-subject",
            }
        ),
    )
    principal = require_staff(authorization="Bearer valid", settings=settings)
    assert principal.role is Role.OWNER
    assert require_owner(principal) == principal
    with pytest.raises(HTTPException, match="Owner approval required"):
        require_owner(
            Principal(email="field@example.com", role=Role.FIELD, subject="field")
        )


@pytest.mark.parametrize(
    "claims",
    [
        {
            "email": "owner@bensonhomesolutions.com",
            "email_verified": False,
            "hd": "bensonhomesolutions.com",
        },
        {"email": "outsider@example.com", "email_verified": True, "hd": "example.com"},
    ],
)
def test_production_google_auth_rejects_untrusted_claims(
    claims: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = production_settings()
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token", MagicMock(return_value=claims)
    )
    with pytest.raises(HTTPException, match="Benson Workspace account required"):
        require_staff(authorization="Bearer invalid", settings=settings)


def test_production_google_auth_rejects_unlisted_workspace_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = production_settings(
        owner_emails="owner@bensonhomesolutions.com",
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "unlisted@bensonhomesolutions.com",
                "email_verified": True,
                "hd": "bensonhomesolutions.com",
                "sub": "unlisted-subject",
            }
        ),
    )
    with pytest.raises(HTTPException, match="Staff account is not authorized"):
        require_staff(authorization="Bearer valid", settings=settings)
    with pytest.raises(HTTPException, match="Staff account is not authorized"):
        require_staff(
            x_dev_staff_email="unlisted@bensonhomesolutions.com",
            settings=Settings(),
        )
