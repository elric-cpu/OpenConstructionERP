import json
import secrets
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

if TYPE_CHECKING:
    from .config import Settings


VerificationStatus = Literal[
    "verified", "paid_license_detected", "verification_unavailable", "mismatch"
]


class DirectoryProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DirectoryIdentity:
    external_user_id: str
    primary_email: str
    org_unit_path: str
    suspended: bool
    verification_status: VerificationStatus
    provider_code: str = ""
    bootstrap_password: str | None = None


class DirectoryProvider(Protocol):
    def create_identity(
        self,
        *,
        primary_email: str,
        given_name: str,
        family_name: str,
        recovery_email: str,
        org_unit_path: str,
    ) -> DirectoryIdentity: ...

    def verify_identity(
        self, *, primary_email: str, org_unit_path: str
    ) -> DirectoryIdentity: ...

    def suspend_identity(self, *, primary_email: str) -> DirectoryIdentity: ...


@dataclass(frozen=True)
class DirectoryProviderConfig:
    delegated_admin: str
    customer_id: str
    service_account_info: dict[str, Any]
    paid_license_skus: tuple[tuple[str, str], ...]
    paid_license_inventory_approved: bool
    production_org_unit: str
    test_org_unit: str

    @classmethod
    def from_settings(cls, settings: "Settings") -> "DirectoryProviderConfig":
        raw_credentials = settings.google_directory_credentials_json.get_secret_value()
        delegated_admin = settings.google_directory_admin
        if not raw_credentials or not delegated_admin:
            raise DirectoryProviderError(
                "directory_not_configured",
                "Google Directory credentials and delegated administrator are required",
            )
        try:
            service_account_info = json.loads(raw_credentials)
        except json.JSONDecodeError as error:
            raise DirectoryProviderError(
                "directory_credentials_invalid",
                "Google Directory credentials are not valid JSON",
            ) from error
        pairs: list[tuple[str, str]] = []
        for item in settings.google_paid_license_skus.split(","):
            product, separator, sku = item.strip().partition(":")
            if separator and product and sku:
                pairs.append((product, sku))
        return cls(
            delegated_admin=delegated_admin.lower(),
            customer_id=settings.google_directory_customer_id,
            service_account_info=service_account_info,
            paid_license_skus=tuple(pairs),
            paid_license_inventory_approved=(
                settings.google_paid_license_skus_approved
            ),
            production_org_unit=settings.google_production_onboarding_ou,
            test_org_unit=settings.google_test_onboarding_ou,
        )

    def org_unit_for(self, environment: str) -> str:
        return (
            self.production_org_unit
            if environment == "production"
            else self.test_org_unit
        )


class GoogleDirectoryProvider:
    directory_base_url = "https://admin.googleapis.com/admin/directory/v1"
    licensing_base_url = "https://licensing.googleapis.com/apps/licensing/v1"
    scopes = (
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/apps.licensing",
    )

    def __init__(self, config: DirectoryProviderConfig):
        self.config = config
        credentials = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            config.service_account_info, scopes=self.scopes
        ).with_subject(config.delegated_admin)
        self.session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]

    def create_identity(
        self,
        *,
        primary_email: str,
        given_name: str,
        family_name: str,
        recovery_email: str,
        org_unit_path: str,
    ) -> DirectoryIdentity:
        existing = self._get_user(primary_email)
        if existing:
            return self._verify_user(existing, org_unit_path)
        bootstrap_password = secrets.token_urlsafe(24)
        response = self.session.post(
            f"{self.directory_base_url}/users",
            json={
                "primaryEmail": primary_email,
                "name": {"givenName": given_name, "familyName": family_name},
                "orgUnitPath": org_unit_path,
                "recoveryEmail": recovery_email,
                "password": bootstrap_password,
                "changePasswordAtNextLogin": True,
                "suspended": False,
                "includeInGlobalAddressList": False,
            },
            timeout=20,
        )
        if response.status_code not in {200, 201}:
            raise DirectoryProviderError(
                f"directory_create_{response.status_code}",
                "Google Directory did not create the identity",
            )
        identity = self._verify_user(self._json(response), org_unit_path)
        return replace(identity, bootstrap_password=bootstrap_password)

    def verify_identity(
        self, *, primary_email: str, org_unit_path: str
    ) -> DirectoryIdentity:
        user = self._get_user(primary_email)
        if not user:
            raise DirectoryProviderError(
                "directory_user_missing", "Google Directory identity was not found"
            )
        return self._verify_user(user, org_unit_path)

    def suspend_identity(self, *, primary_email: str) -> DirectoryIdentity:
        response = self.session.patch(
            f"{self.directory_base_url}/users/{quote(primary_email, safe='')}",
            json={"suspended": True},
            timeout=20,
        )
        if response.status_code != 200:
            raise DirectoryProviderError(
                f"directory_suspend_{response.status_code}",
                "Google Directory did not suspend the identity",
            )
        user = self._json(response)
        return DirectoryIdentity(
            external_user_id=str(user.get("id", "")),
            primary_email=str(user.get("primaryEmail", primary_email)).lower(),
            org_unit_path=str(user.get("orgUnitPath", "")),
            suspended=bool(user.get("suspended")),
            verification_status="verified" if user.get("suspended") else "mismatch",
            provider_code="directory_suspended",
        )

    def _get_user(self, primary_email: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.directory_base_url}/users/{quote(primary_email, safe='')}",
            timeout=20,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DirectoryProviderError(
                f"directory_read_{response.status_code}",
                "Google Directory identity could not be read",
            )
        return self._json(response)

    def _verify_user(
        self, user: dict[str, Any], expected_org_unit: str
    ) -> DirectoryIdentity:
        email = str(user.get("primaryEmail", "")).lower()
        org_unit = str(user.get("orgUnitPath", ""))
        suspended = bool(user.get("suspended"))
        if org_unit != expected_org_unit or suspended:
            return DirectoryIdentity(
                external_user_id=str(user.get("id", "")),
                primary_email=email,
                org_unit_path=org_unit,
                suspended=suspended,
                verification_status="mismatch",
                provider_code="directory_identity_mismatch",
            )
        if (
            not self.config.paid_license_skus
            or not self.config.paid_license_inventory_approved
        ):
            return DirectoryIdentity(
                external_user_id=str(user.get("id", "")),
                primary_email=email,
                org_unit_path=org_unit,
                suspended=suspended,
                verification_status="verification_unavailable",
                provider_code="paid_sku_inventory_missing",
            )
        for product_id, sku_id in self.config.paid_license_skus:
            response = self.session.get(
                f"{self.licensing_base_url}/product/{quote(product_id, safe='')}"
                f"/sku/{quote(sku_id, safe='')}/user/{quote(email, safe='')}",
                timeout=20,
            )
            if response.status_code == 200:
                return DirectoryIdentity(
                    external_user_id=str(user.get("id", "")),
                    primary_email=email,
                    org_unit_path=org_unit,
                    suspended=suspended,
                    verification_status="paid_license_detected",
                    provider_code=f"paid_license:{product_id}:{sku_id}",
                )
            if response.status_code != 404:
                return DirectoryIdentity(
                    external_user_id=str(user.get("id", "")),
                    primary_email=email,
                    org_unit_path=org_unit,
                    suspended=suspended,
                    verification_status="verification_unavailable",
                    provider_code=f"licensing_read_{response.status_code}",
                )
        return DirectoryIdentity(
            external_user_id=str(user.get("id", "")),
            primary_email=email,
            org_unit_path=org_unit,
            suspended=suspended,
            verification_status="verified",
            provider_code="no_paid_license",
        )

    @staticmethod
    def _json(response: Any) -> dict[str, Any]:
        body = response.json()
        if not isinstance(body, dict):
            raise DirectoryProviderError(
                "directory_response_invalid", "Google Directory returned invalid data"
            )
        return body


def directory_provider_for(settings: "Settings") -> tuple[DirectoryProvider, str]:
    config = DirectoryProviderConfig.from_settings(settings)
    if settings.environment == "production" and (
        not config.paid_license_skus or not config.paid_license_inventory_approved
    ):
        raise DirectoryProviderError(
            "paid_sku_inventory_required",
            "Production paid-license SKU inventory is required",
        )
    return GoogleDirectoryProvider(config), config.org_unit_for(settings.environment)
