from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import get_settings
from app.core.edition import normalize_project_context, validate_locale
from app.core.email import EmailMessage
from app.core.job_runner import get_handler
from app.modules.benson_workers.jobs import PROVISION_DIRECTORY_JOB, SEND_ACTIVATION_JOB
from app.modules.benson_workers.providers import ResendEmailBackend, provider_status
from app.modules.projects.schemas import ProjectCreate


@pytest.fixture
def benson_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OE_EDITION", "benson")
    monkeypatch.setenv("OE_SUPPORTED_LOCALES", "en")
    monkeypatch.setenv("OE_DEFAULT_LOCALE", "en-US")
    monkeypatch.setenv("OE_DEFAULT_REGION", "benson_eastern_oregon")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_benson_rejects_non_english_locale(benson_env) -> None:
    assert validate_locale("en-US") == "en-US"
    with pytest.raises(ValueError, match="Unsupported locale"):
        validate_locale("fr")


@pytest.mark.parametrize("timezone", ["America/Boise", "America/Los_Angeles"])
def test_eastern_oregon_context_accepts_project_timezone(benson_env, timezone: str) -> None:
    context = normalize_project_context("Malheur", "City of Ontario", timezone)
    assert context["county"] == "Malheur"
    assert context["timezone"] == timezone


def test_eastern_oregon_context_has_no_county_whitelist(benson_env) -> None:
    context = normalize_project_context("A newly formed county", "Local authority", "America/Boise")
    assert context["county"] == "A newly formed county"


def test_benson_project_requires_jurisdiction_and_timezone(benson_env) -> None:
    with pytest.raises(ValidationError, match="Benson projects require"):
        ProjectCreate(name="Missing context")

    project = ProjectCreate(
        name="Ontario remodel",
        county="Malheur",
        local_jurisdiction="City of Ontario",
        timezone="America/Boise",
    )
    assert project.region == "benson_eastern_oregon"
    assert project.locale == "en-US"


def test_invalid_iana_timezone_is_rejected(benson_env) -> None:
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        normalize_project_context("Union", "City of La Grande", "Pacific/Oregon")


def test_benson_manifests_are_enabled_only_for_benson(benson_env) -> None:
    environment = os.environ.copy()
    environment["OE_EDITION"] = "benson"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.modules.benson_edition.manifest import manifest; "
            "assert manifest.enabled and 'benson_operations' in manifest.depends",
        ],
        cwd=Path(__file__).parents[2],
        env=environment,
        check=False,
    )
    assert result.returncode == 0


def test_benson_partner_pack_extends_us_profile() -> None:
    pack_root = Path(__file__).parents[3] / "packs" / "benson-eastern-oregon" / "src"
    sys.path.insert(0, str(pack_root))
    try:
        module = importlib.import_module("openconstructionerp_benson_eastern_oregon")
        manifest = module.MANIFEST
    finally:
        sys.path.remove(str(pack_root))

    assert manifest.metadata["extends"] == "us-rsmeans"
    assert manifest.metadata["county_policy"] == "open-no-whitelist"
    assert manifest.metadata["timezone_scope"] == "project"
    assert manifest.demo_template_ids == ["commercial-denver", "medical-us"]


def test_spa_fallback_preserves_service_404s(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index = tmp_path / "index.html"
    index.write_text("<html>Benson</html>", encoding="utf-8")

    from app import cli_static

    monkeypatch.setattr(cli_static, "get_frontend_dir", lambda: tmp_path)
    app = FastAPI()
    cli_static.mount_frontend(app)
    client = TestClient(app)

    assert client.get("/projects/example").text == "<html>Benson</html>"
    assert client.get("/api/missing").status_code == 404
    assert client.get("/health/missing").status_code == 404
    assert client.get("/metrics").status_code == 404


@pytest.mark.asyncio
async def test_resend_adapter_uses_existing_email_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "email-123"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        backend = ResendEmailBackend(
            get_settings().model_copy(update={"resend_api_key": "secret", "resend_from": "Benson <leads@example.com>"}),
            client,
        )
        result = await backend.send(
            EmailMessage(to="employee@example.com", subject="Activate", html_body="<p>Ready</p>")
        )

    assert result.ok is True
    assert result.reason == "email-123"
    assert captured["authorization"] == "Bearer secret"


def test_provider_status_is_fail_closed_by_default() -> None:
    status = provider_status(get_settings())
    assert status["google_directory"]["enabled"] is False


def test_celery_bootstrap_registers_benson_handlers() -> None:
    importlib.import_module("app.modules.benson_workers.celery_app")

    assert get_handler(PROVISION_DIRECTORY_JOB) is not None
    assert get_handler(SEND_ACTIVATION_JOB) is not None
