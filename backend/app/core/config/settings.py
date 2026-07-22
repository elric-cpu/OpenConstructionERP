"""Main settings configuration that composes domain-specific settings."""

import logging
import re
import os
from pathlib import Path
from typing import Tuple

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .app import AppSettings
from .audit import AuditSettings
from .auth import AuthSettings
from .bim import BIMSettings
from .cwicr import CWICRSettings
from .database import DatabaseSettings
from .email import EmailSettings
from .external_services import ExternalServicesSettings
from .pointcloud import PointCloudSettings
from .rate_limits import RateLimitsSettings
from .redis import RedisSettings
from .storage import StorageSettings
from .validation import ValidationSettings

_logger = logging.getLogger("openestimate.config")

# Whether we've already logged the dev-default JWT warning so a unit
# test that instantiates Settings() repeatedly (or an app that hot-reloads
# the config) doesn't spam the log. Reset by the test suite via the
# `reset_jwt_dev_warning` helper below.
_DEV_JWT_WARNING_EMITTED = False


def reset_jwt_dev_warning() -> None:
    """Reset the once-per-process dev-default JWT warning latch.

    Test-only helper. The production path emits the warning exactly
    once on first "Settings()" instantiation; tests that exercise
    that path multiple times call this between cases to re-arm the
    latch.
    """
    global _DEV_JWT_WARNING_EMITTED
    _DEV_JWT_WARNING_EMITTED = False


def _read_pyproject_version() -> str | None:
    """Best-effort parse of ``version = "..."`` from backend/pyproject.toml.

    Used when the package isn't installed (``pip install -e .`` not run).
    Walks up from this file so it works whether CWD is repo root, backend/,
    or a unit-test runner.
    """
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                return None
            match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if match:
                return match.group(1)
            return None
    return None


def _detect_version() -> str:
    """Pick the version /api/health should report.

    When running from the source tree (the common dev workflow:
    ``cd backend && python -m uvicorn app.main:create_app --factory``),
    the *source* file is what's actually executing - but
    ``importlib.metadata.version`` returns whatever is in ``site-packages``
    if a stale ``pip install openconstructionerp==X`` happened earlier.
    That made ``/api/health`` claim a wrong version after every dev
    edit and made it impossible to tell, in a QA session, whether a
    just-edited file was actually serving requests.

    Resolution order (first hit wins):
      1. If ``app/__init__.py`` lives outside ``site-packages`` and a
         ``pyproject.toml`` is on disk above it, read that - the source
         tree is the source of truth.
      2. Otherwise, ``importlib.metadata.version("openconstructionerp")``.
      3. ``0.0.0+local`` sentinel when all else fails.
    """
    here = Path(__file__).resolve()
    if "site-packages" not in str(here):
        from_source = _read_pyproject_version()
        if from_source:
            return from_source
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("openconstructionerp")
    except Exception:  # PackageNotFoundError
        return _read_pyproject_version() or "0.0.0+local"


def build_provenance_tag(version: str) -> str:
    """Derive the opaque build-provenance signature reported by /api/health.

    Combines a fixed seed with a content-hash component (sha256 of the
    running version) so the value rotates per release like a routine
    build checksum. The seed bytes XOR-fold (key 0x55) into the authorship
    string; removing or altering the seed changes the published
    ``signature`` field, but the value is otherwise inert (read-only
    metadata - nothing branches on it).
    """
    import hashlib as _h

    _seed = bytes(
        b ^ 0x55
        for b in (
            b"\x1a\x25\x30\x3b\x16\x3a\x3b\x26\x21\x27\x20\x36\x21\x3c\x3a\x3b"
            b"\x10\x07\x05\x78\x11\x11\x16\x78\x16\x02\x1c\x16\x07"
        )
    )
    _content = _h.sha256(version.encode("utf-8")).digest()
    return _h.sha256(_seed + _content).hexdigest()[:20]


def _find_env_file() -> list[str]:
    """Locate backend/.env regardless of the process CWD.

    Uvicorn may be launched from the repo root, backend/, or anywhere else,
    and pydantic-settings's default ``env_file=".env"`` is resolved against
    CWD - which silently drops the whole file when the CWD is "wrong".
    A missing JWT_SECRET rotates Fernet keys every boot and makes stored
    AI API keys undecryptable. Anchor to the package directory instead.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / ".env",  # backend/.env (app/ is one up)
        here.parent.parent.parent / ".env",  # repo root .env (optional)
    ]
    return [str(p) for p in candidates if p.is_file()]


def _canonicalize_db_url(url: str, *, driver: str) -> str:
    """Canonicalize a PostgreSQL connection URL to ``postgresql+<driver>://``.

    Managed-Postgres providers (Heroku, Supabase, Railway, Render, Fly) hand
    out ``postgres://`` URLs, and some tutorials use ``postgres+asyncpg://``.
    SQLAlchemy removed the ``postgres`` dialect alias in 1.4, so either form
    makes the engine raise ``NoSuchModuleError: Can't load plugin:
    sqlalchemy.dialects:postgres`` (or ``...:postgres.asyncpg`` once a driver is
    attached). Rewrite any ``postgres`` / ``postgresql`` URL -- with or without a
    driver -- to the dialect and driver this engine actually needs, so the same
    ``DATABASE_URL`` works whether the operator pasted a cloud connection string
    or our own canonical form. SQLite and blank URLs pass through untouched.
    """
    if not url:
        return url
    scheme = url.split("://", 1)[0].lower()
    if not scheme.startswith("postgres"):
        return url
    try:
        from sqlalchemy.engine import make_url

        return make_url(url).set(drivername=f"postgresql+{driver}").render_as_string(hide_password=False)
    except Exception:  # noqa: BLE001 - never block boot on a URL we cannot parse
        return url


class Settings(
    AppSettings,
    AuditSettings,
    AuthSettings,
    BIMSettings,
    CWICRSettings,
    DatabaseSettings,
    EmailSettings,
    ExternalServicesSettings,
    PointCloudSettings,
    RateLimitsSettings,
    RedisSettings,
    StorageSettings,
    ValidationSettings,
    BaseSettings,
):
    """OpenConstructionERP application settings.

    This class combines all domain-specific settings into a single
    settings object for backward compatibility.
    """

    model_config = SettingsConfigDict(
        env_file=_find_env_file() or ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Accept the documented ``OE_``-prefixed env vars as well as bare names.

        Historically the settings model declared no ``env_prefix``, so each
        field bound only to its bare upper-cased name (``REGISTRATION_MODE``,
        ``DATABASE_URL``, ...). But the docstrings, deployment guides and
        examples throughout the project use the brand-namespaced ``OE_``
        prefix (``OE_REGISTRATION_MODE``, ``OE_SLOW_QUERY_MS``, ...). An
        operator who followed the docs and set ``OE_REGISTRATION_MODE=closed``
        got the prefixed variable silently ignored and the default applied -
        a confusing, hard-to-diagnose footgun reported from production.

        We add a second environment source that strips an ``OE_`` prefix so
        both spellings populate the same field. The bare-name source keeps
        priority, so existing deployments that already set the unprefixed
        variables are completely unaffected; the prefixed source only fills a
        field the bare name did not already provide.
        """
        oe_prefixed_env = EnvSettingsSource(
            settings_cls,
            case_sensitive=False,
            env_prefix="OE_",
        )
        return (
            init_settings,
            env_settings,
            oe_prefixed_env,
            dotenv_settings,
            file_secret_settings,
        )

    # ── Validators ───────────────────────────────────────────────────────
    @field_validator("database_url", mode="after")
    @classmethod
    def _canonical_async_db_url(cls, value: str) -> str:
        """Accept any postgres:// form for the async engine, normalize to asyncpg."""
        return _canonicalize_db_url(value, driver="asyncpg")

    @field_validator("database_sync_url", mode="after")
    @classmethod
    def _canonical_sync_db_url(cls, value: str) -> str:
        """Accept any postgres:// form for the sync engine, normalize to psycopg2."""
        return _canonicalize_db_url(value, driver="psycopg2")

    @model_validator(mode="after")
    def _cross_fill_db_urls(self) -> "Settings":
        """Derive the missing async/sync DB URL when only one is supplied.

        Operators commonly set only ``DATABASE_URL`` (the async one). Mirror
        whichever side points at Postgres into the other when that other side
        is blank, so alembic, the CWICR bulk import and the migration helper
        always agree on the same cluster instead of one of them falling back to
        an unconfigured engine.
        """
        if self.database_url.startswith("postgresql") and not self.database_sync_url.strip():
            self.database_sync_url = _canonicalize_db_url(self.database_url, driver="psycopg2")
        elif self.database_sync_url.startswith("postgresql") and not self.database_url.strip():
            self.database_url = _canonicalize_db_url(self.database_sync_url, driver="asyncpg")
        return self

    # ── Computed ─────────────────────────────────────────────────────────
    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret == "openestimate-local-dev-key"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @model_validator(mode="after")
    def _refuse_default_jwt_in_non_dev(self) -> "Settings":
        """Refuse to start in staging/production with a weak JWT secret.

        Rejects three failure modes when ``APP_ENV != "development"``:

        1. ``jwt_secret`` is the bundled dev default - published in the
           public repo, admin-forgeable by anyone who can `git clone`.
        2. ``jwt_secret`` matches any other known weak / boilerplate
           value (``change-me``, ``secret``, ``jwt-secret``, etc.) - these
           leak into production all the time via copy-paste.
        3. ``jwt_secret`` is shorter than 32 characters - HS256 token
           forgery becomes computationally tractable below that length.

        In ``development`` the guard is a no-op so a fresh ``docker compose up``
        works without any .env. We still log a one-shot WARNING on the dev
        default with the secret length and a reminder so the operator sees
        an unmistakable nudge to set ``OE_JWT_SECRET`` before shipping.

        To override for self-hosters: set ``OE_JWT_SECRET`` (or ``JWT_SECRET``)
        to a fresh value, e.g.
        ``python -c "import secrets;print(secrets.token_urlsafe(32))"``
        or ``openssl rand -hex 32``.
        """
        secret = self.jwt_secret or ""
        is_weak_default = secret in _JWT_KNOWN_WEAK_SECRETS
        is_too_short = len(secret) < _JWT_SECRET_MIN_LENGTH

        if self.app_env != "development":
            if is_weak_default:
                raise RuntimeError(
                    f"Refusing to start: JWT_SECRET is a well-known weak default "
                    f"({secret!r}) but APP_ENV is {self.app_env!r}. Known-weak "
                    f"secrets are admin-forgeable by anyone who reads the public "
                    f"OpenConstructionERP source. Set OE_JWT_SECRET to a fresh "
                    f"random value of at least {_JWT_SECRET_MIN_LENGTH} "
                    f"characters, e.g.\n"
                    f'  python -c "import secrets;print(secrets.token_urlsafe(32))"\n'
                    f"  openssl rand -hex 32"
                )
            if is_too_short:
                raise RuntimeError(
                    f"Refusing to start: JWT_SECRET is only {len(secret)} "
                    f"characters but APP_ENV is {self.app_env!r}. HS256 token "
                    f"forgery is computationally tractable below "
                    f"{_JWT_SECRET_MIN_LENGTH} characters. Set OE_JWT_SECRET to "
                    f"a fresh random value of at least "
                    f"{_JWT_SECRET_MIN_LENGTH} characters, e.g.\n"
                    f'  python -c "import secrets;print(secrets.token_urlsafe(32))"\n'
                    f"  openssl rand -hex 32"
                )

        # Development with the bundled default - log a one-shot WARNING so
        # the operator is reminded to override before promoting the
        # environment. We deliberately log the length (not the value) so
        # the warning is informative without leaking the secret if log
        # files end up shipped off-host.
        if self.app_env == "development" and is_weak_default:
            global _DEV_JWT_WARNING_EMITTED
            if not _DEV_JWT_WARNING_EMITTED:
                _logger.warning(
                    "JWT_SECRET is the bundled development default "
                    "(length=%d). This is fine for local dev but MUST be "
                    "overridden in staging/production via OE_JWT_SECRET. "
                    "Generate a fresh secret with: "
                    'python -c "import secrets;print(secrets.token_urlsafe(32))"',
                    len(secret),
                )
                _DEV_JWT_WARNING_EMITTED = True

        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_frontend_url(self) -> str:
        """URL used in outbound email links.

        Prefers the explicit ``FRONTEND_URL`` setting; falls back to the
        first CORS origin so a zero-config dev install still produces
        clickable reset links pointing at Vite's 5173.
        """
        if self.frontend_url:
            return self.frontend_url.rstrip("/")
        origins = self.cors_origins
        return origins[0].rstrip("/") if origins else "http://localhost:5173"


def get_settings() -> Settings:
    """Dependency that returns the application settings."""
    return Settings()


# ── Constants ──────────────────────────────────────────────────────────────
_JWT_KNOWN_WEAK_SECRETS = frozenset(
    {
        "openestimate-local-dev-key",
        "change-me",
        "secret",
        "jwt-secret",
        "jwt_secret",
        "changeme",
        "123456",
        "password",
    }
)
_JWT_SECRET_MIN_LENGTH = 32
