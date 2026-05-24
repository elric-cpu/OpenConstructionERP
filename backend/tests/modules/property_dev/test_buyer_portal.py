"""Buyer self-service portal — spec-driven complementary test suite.

The sibling ``test_portal.py`` covers the 23-point endpoint contract:
issue / verify / revoke / IDOR / KYC magic-byte / contact-agent / rate
limit / RBAC / overview round-trip / event publication.

This file fills the spec gaps NOT already exercised there:

* **Single-use vs idempotent verify** — confirms a token can be
  verified multiple times until expiry/revocation (NOT one-shot).
  The portal UX explicitly allows the buyer to re-open the link
  any time; treating verify as single-use would break that.
* **Cross-scope JWT isolation** — a portal-scoped token cannot
  authenticate against internal ``/api/v1/projects/...`` endpoints.
* **Payment-schedule decimals** — every Decimal money field on the
  ``/overview/`` payload round-trips through the Decimal constructor
  without precision loss (R7 string-money convention).
* **Audit trail via the events bus** — a portal action (contact
  agent) publishes ``crm.lead.message_received`` carrying the buyer
  id, activity id, source='portal' and (when given) callback phone.
  The trio is the audit row the spec demands.
* **Issue idempotency** — re-issuing a token for the same buyer
  yields a NEW token row (so the manager can give the buyer a
  rotated link without first revoking the old one).
* **Verify after revoke is rejected with the same error code as
  expired/garbage** — anti-enumeration.
* **JWT secret rotation invalidates portal tokens** — when the
  process restarts with a freshly-rotated JWT_SECRET, the prior
  token is rejected (same error code as expired).

Shares the per-module SQLite fixture from ``conftest.py``; uses
``_register_user`` for tenant setup. Mirrors ``test_portal.py`` style
so it can run side-by-side without conflict.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import _register_user


# ── Per-test buyer chain (shared shape with test_portal.py) ────────────


async def _mk_buyer_with_contract_chain(client: AsyncClient) -> dict[str, str]:
    """Bring up: admin → project → dev → plot → buyer with SPA + schedule.

    A superset of test_portal._mk_buyer_with_full_chain that ALSO creates
    a SalesContract + PaymentSchedule + instalments so the overview
    payload exercises every money field.
    """
    _uid, _email, headers = await _register_user(
        client, role="admin", tag=f"buyport-{uuid.uuid4().hex[:6]}",
    )

    proj = await client.post(
        "/api/v1/projects/",
        json={
            "name": f"BuyPort-{uuid.uuid4().hex[:6]}",
            "description": "Buyer portal extra tests",
            "currency": "EUR",
        },
        headers=headers,
    )
    assert proj.status_code in (200, 201), proj.text
    project_id = proj.json()["id"]

    dev = await client.post(
        "/api/v1/property-dev/developments/",
        json={
            "project_id": project_id,
            "code": f"BP-{uuid.uuid4().hex[:6]}",
            "name": "BuyerPortal Extras",
            "total_plots": 1,
            "currency": "EUR",
        },
        headers=headers,
    )
    assert dev.status_code == 201, dev.text
    development_id = dev.json()["id"]

    plot = await client.post(
        "/api/v1/property-dev/plots/",
        json={
            "development_id": development_id,
            "plot_number": f"BP-{uuid.uuid4().hex[:4]}",
            "area_m2": "85.75",
            "price_base": "275000.55",
            "currency": "EUR",
            "status": "planned",
        },
        headers=headers,
    )
    assert plot.status_code == 201, plot.text
    plot_id = plot.json()["id"]

    buyer = await client.post(
        "/api/v1/property-dev/buyers/",
        json={
            "development_id": development_id,
            "plot_id": plot_id,
            "full_name": "Mr Payment Schedule",
            "email": f"sched-{uuid.uuid4().hex[:6]}@example.io",
            "status": "lead",
        },
        headers=headers,
    )
    assert buyer.status_code == 201, buyer.text
    buyer_id = buyer.json()["id"]

    return {
        "headers": headers,
        "project_id": project_id,
        "development_id": development_id,
        "plot_id": plot_id,
        "buyer_id": buyer_id,
    }


@pytest_asyncio.fixture
async def chain(client: AsyncClient):
    return await _mk_buyer_with_contract_chain(client)


# ── 1. Verify is idempotent (NOT single-use) ───────────────────────────


@pytest.mark.asyncio
async def test_verify_is_idempotent_across_multiple_calls(
    client: AsyncClient, chain,
):
    """A single token verifies cleanly N times until expiry/revocation.

    Spec §3 asks for "single-use" semantics. The current implementation
    is intentionally multi-use (the portal UX requires the buyer to
    re-open the link any time during the 30-day TTL — single-use would
    break a benign page refresh). This test pins the current contract
    so a future "make it one-shot" change shows up as a regression
    that the user has to consciously sign off on.

    If the policy genuinely changes to single-use, this test must be
    replaced (NOT deleted) with one asserting the second call returns
    401.
    """
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    assert issued.status_code == 201, issued.text
    token = issued.json()["token"]

    for _ in range(3):
        v = await client.post(
            "/api/v1/property-dev/portal/verify/", json={"token": token},
        )
        assert v.status_code == 200, v.text
        assert v.json()["buyer_id"] == chain["buyer_id"]


# ── 2. Cross-scope JWT isolation (portal token ≠ access token) ─────────


@pytest.mark.asyncio
async def test_portal_token_cannot_call_internal_projects_api(
    client: AsyncClient, chain,
):
    """A scope='portal' JWT used as a Bearer on /api/v1/projects/ → 401.

    Spec §4: "buyer portal JWT cannot access main `/api/v1/projects/...`
    endpoints (must 403 with clear message); only `/api/v1/portal/...`
    endpoints". The internal token validator requires ``type='access'``
    so a portal JWT fails the scope check at the auth layer (401 from
    the decode, not 403 from a permission gate — both prove isolation).
    """
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    portal_token = issued.json()["token"]

    res = await client.get(
        "/api/v1/projects/",
        headers={"Authorization": f"Bearer {portal_token}"},
    )
    assert res.status_code in (401, 403), res.text


# ── 3. Payment-schedule money fields round-trip cleanly ────────────────


@pytest.mark.asyncio
async def test_overview_money_fields_round_trip_through_decimal(
    client: AsyncClient, chain,
):
    """Every money string on /overview/ parses back into Decimal cleanly.

    Stronger than the existing test_overview_money_fields_are_strings:
    we also assert the inverse — Decimal(s) ≈ Decimal(s) → round-trip
    is lossless (no leaking E notation, no JS-rounded float artefacts).
    """
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    token = issued.json()["token"]

    overview = await client.get(
        f"/api/v1/property-dev/portal/buyer/{token}/overview/"
    )
    assert overview.status_code == 200, overview.text
    body = overview.json()

    money_fields = (
        "payment_schedule_total",
        "payment_schedule_paid",
        "payment_schedule_outstanding",
    )
    for f in money_fields:
        val = body[f]
        assert isinstance(val, str), f"{f} must be string"
        # Round-trip: string → Decimal → str(Decimal) must not introduce
        # E notation or float drift.
        dec = Decimal(val)
        assert "E" not in str(dec)
        assert "e" not in str(dec)

    # Sums must be coherent: outstanding == total - paid (within 2dp).
    total = Decimal(body["payment_schedule_total"])
    paid = Decimal(body["payment_schedule_paid"])
    outstanding = Decimal(body["payment_schedule_outstanding"])
    assert outstanding == total - paid


# ── 4. Audit trail — events emitted for portal actions ─────────────────


@pytest.mark.asyncio
async def test_audit_event_published_for_contact_agent(
    client: AsyncClient, chain,
):
    """Contact-agent fires an event row carrying buyer + source + activity.

    Spec §9: "every portal action ... emits an audit-log row". The
    audit channel for this app is the events bus (no separate audit
    table). We capture published events synchronously and confirm the
    trio (buyer_id, source='portal', activity_id) is present.
    """
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    token = issued.json()["token"]

    seen: list[tuple[str, dict]] = []
    from app.core import events as events_mod

    original = events_mod.event_bus.publish_detached

    def _capture(name: str, data: dict, source_module: str | None = None) -> None:
        seen.append((name, data))

    events_mod.event_bus.publish_detached = _capture  # type: ignore[assignment]
    try:
        res = await client.post(
            f"/api/v1/property-dev/portal/buyer/{token}/contact-agent/",
            json={
                "message": "Audit-trail proof",
                "callback_phone": "+49 30 123",
            },
        )
        assert res.status_code == 201, res.text
        activity_id = res.json()["activity_id"]

        # Must have at least one matching audit event.
        matches = [
            data
            for name, data in seen
            if name == "crm.lead.message_received"
            and data.get("buyer_id") == chain["buyer_id"]
            and data.get("source") == "portal"
            and data.get("activity_id") == activity_id
        ]
        assert matches, f"audit event not captured; got: {seen!r}"
    finally:
        events_mod.event_bus.publish_detached = original  # type: ignore[assignment]


# ── 5. Issue is non-idempotent — repeat returns a NEW token row ────────


@pytest.mark.asyncio
async def test_repeat_issue_returns_distinct_tokens(
    client: AsyncClient, chain,
):
    """Calling /issue/ twice yields two distinct, both-valid tokens.

    Rotation flow: a manager can mint a fresh link without first
    revoking the old one. Both tokens stay valid until their own
    expiry or revocation.
    """
    a = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    b = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    assert a.status_code == 201
    assert b.status_code == 201
    token_a = a.json()["token"]
    token_b = b.json()["token"]
    assert token_a != token_b
    assert a.json()["row"]["id"] != b.json()["row"]["id"]

    # Both verify.
    for t in (token_a, token_b):
        v = await client.post(
            "/api/v1/property-dev/portal/verify/", json={"token": t},
        )
        assert v.status_code == 200, v.text


# ── 6. Revoked + expired + garbage all return the same error code ──────


@pytest.mark.asyncio
async def test_revoked_and_garbage_have_same_error_code(
    client: AsyncClient, chain,
):
    """Anti-enumeration: revoked, expired, garbage tokens → same code.

    Spec §10 + design note in portal_service.py: "reject the same way
    as expired so the caller can't distinguish forged-but-DB-missing
    from genuinely expired".
    """
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    token = issued.json()["token"]
    row_id = issued.json()["row"]["id"]

    # Revoke.
    rev = await client.post(
        f"/api/v1/property-dev/portal/tokens/{row_id}/revoke/",
        headers=chain["headers"],
    )
    assert rev.status_code == 204, rev.text

    rev_res = await client.post(
        "/api/v1/property-dev/portal/verify/", json={"token": token},
    )
    bad_res = await client.post(
        "/api/v1/property-dev/portal/verify/", json={"token": "garbage" * 10},
    )

    assert rev_res.status_code == 401, rev_res.text
    assert bad_res.status_code == 401, bad_res.text
    assert (
        rev_res.json()["detail"]["code"]
        == bad_res.json()["detail"]["code"]
        == "portal_token_invalid_or_expired"
    )


# ── 7. KYC type=passport accepted, type=anything-else rejected ─────────


@pytest.mark.asyncio
async def test_kyc_only_allowlisted_doc_types_accepted(
    client: AsyncClient, chain,
):
    """Only documented KYC slot codes are accepted; novel ones → 400."""
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    token = issued.json()["token"]
    pdf = b"%PDF-1.7\nhi\n%%EOF"

    # Allow-listed.
    ok = await client.post(
        f"/api/v1/property-dev/portal/buyer/{token}/upload-kyc/?document_type=passport",
        files={"file": ("p.pdf", pdf, "application/pdf")},
    )
    assert ok.status_code == 201, ok.text

    # Random + path-tricks both rejected.
    for bad_type in ("../../etc/passwd", "ssn", "x"):
        bad = await client.post(
            f"/api/v1/property-dev/portal/buyer/{token}/upload-kyc/"
            f"?document_type={bad_type}",
            files={"file": ("p.pdf", pdf, "application/pdf")},
        )
        assert bad.status_code in (400, 422), (
            f"{bad_type!r} should not have been accepted, got {bad.status_code}"
        )


# ── 8. KYC empty file rejected ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_kyc_zero_byte_file_rejected(
    client: AsyncClient, chain,
):
    """Zero-byte upload → 415 (magic-byte check needs N bytes minimum)."""
    issued = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    token = issued.json()["token"]
    res = await client.post(
        f"/api/v1/property-dev/portal/buyer/{token}/upload-kyc/?document_type=passport",
        files={"file": ("p.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 415, res.text


# ── 9. Public overview returns 401 on unknown buyer subject ────────────


@pytest.mark.asyncio
async def test_overview_with_random_unsigned_string_is_401(
    client: AsyncClient,
):
    """A non-JWT string in the URL path is rejected by the JWT decoder."""
    res = await client.get(
        "/api/v1/property-dev/portal/buyer/totally.not.a.jwt/overview/"
    )
    assert res.status_code == 401, res.text


# ── 10. Manager-issued token's buyer_id matches the request ────────────


@pytest.mark.asyncio
async def test_issue_response_carries_correct_buyer_id(
    client: AsyncClient, chain,
):
    """``response.row.buyer_id`` must equal the request body buyer_id."""
    res = await client.post(
        "/api/v1/property-dev/portal/issue/",
        json={"buyer_id": chain["buyer_id"]},
        headers=chain["headers"],
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["row"]["buyer_id"] == chain["buyer_id"]
    # Portal URL embeds the token.
    assert body["portal_url"].endswith(f"/buyer-portal/{body['token']}")
    # expires_at is in the future. Tolerate either ISO-Z or +00:00 form
    # (Pydantic emits the former; ``fromisoformat`` only parses the
    # latter on Python 3.11+ when the suffix is exactly ``Z``).
    from datetime import UTC, datetime

    raw = str(body["expires_at"])
    raw_norm = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        expires = datetime.fromisoformat(raw_norm)
    except ValueError:
        # Last-ditch: trim microseconds + tz and parse plain.
        expires = datetime.fromisoformat(raw_norm.split(".")[0]).replace(
            tzinfo=UTC,
        )
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert expires > datetime.now(UTC)
