#!/usr/bin/env python3
"""Demo registration API with email verification.

Flow:
1. POST /register -> saves with verified=false, sends confirmation email
2. GET /verify?token=X -> marks as verified, redirects to demo
3. Admin notification on successful verification

Supports: SMTP (Gmail/any) or Resend API.
Listens on port 8891.

Environment variables:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM  — for SMTP
  RESEND_API_KEY, RESEND_FROM                              — for Resend API
  ADMIN_EMAIL                                              — admin notification
  BASE_URL                                                 — site URL
"""

import hashlib
import json
import os
import re
import secrets
import smtplib
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8891

# ─── Anti-spam / fake-identity gate ──────────────────────────────────────
#
# Goal: stop the firehose of "Test / 123 / тест / asdf" registrations
# from polluting the demo-signups list and (more importantly) auto-
# verifying themselves into the live demo. Two layers:
#
#   1. Junk-name detection — rejects literal "test", "тест", "123",
#      "asdf", repeated single chars, all-digit names, and obvious
#      keyboard runs ("qwerty", "asdf", "zxcv").
#   2. Disposable / fake email domain detection — rejects mailinator-
#      style throwaway addresses, plus the specific domains we already
#      saw being abused in production data (lealking.com, nyspring.com,
#      nazisat.com, agoalz.com, algarr.com).
#
# Tuning principle: prefer false-negatives over false-positives. A real
# user named "Li" or with a personal gmail must always pass. Only
# reject when *strongly* confident the input is junk.

_DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    # Well-known throwaway providers
    "mailinator.com", "tempmail.com", "tempmail.net", "temp-mail.org",
    "10minutemail.com", "10minutemail.net", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "throwawaymail.com",
    "yopmail.com", "trashmail.com", "trashmail.net", "fakeinbox.com",
    "sharklasers.com", "getairmail.com", "dispostable.com",
    "mailnesia.com", "maildrop.cc", "mintemail.com", "mohmal.com",
    "dropmail.me", "harakirimail.com", "mvrht.net", "spam4.me",
    "tmpmail.org", "tmpmail.net", "spamgourmet.com", "discard.email",
    "incognitomail.com", "anonbox.net", "mytrashmail.com",
    # Caught in our production logs (Apr 2026 batch)
    "lealking.com", "nyspring.com", "nazisat.com", "agoalz.com",
    "algarr.com",
    # Obvious test placeholders
    "example.com", "example.org", "example.net", "test.com", "test.test",
    "localhost", "localhost.localdomain", "invalid", "invalid.com",
    "qq.com.test", "asdf.com", "qwerty.com", "123.com", "123.ry",
})

# Email local-part patterns we always reject (case-insensitive).
# Tied to common spam shapes — be conservative.
_JUNK_LOCALPART_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test\d*$", re.I),
    re.compile(r"^tests\d*$", re.I),
    re.compile(r"^demo\d*$", re.I),
    re.compile(r"^asdf*$", re.I),
    re.compile(r"^qwer(ty)?\d*$", re.I),
    re.compile(r"^abc\d*$", re.I),
    re.compile(r"^123+$"),
    re.compile(r"^a+$", re.I),
    re.compile(r"^x+$", re.I),
    re.compile(r"^(.)\1{2,}$"),  # "aaaa", "1111", "...."
)

# Junk first/last name shapes. Lower-cased before matching.
_JUNK_NAME_LITERALS: frozenset[str] = frozenset({
    "test", "tests", "testing", "тест", "тестт", "тесттт",
    "demo", "demouser", "user", "юзер",
    "asdf", "asdfg", "asdfgh", "asd", "asdq", "asdwq", "asde",
    "qwer", "qwerty", "qwertyu", "qwe",
    "zxcv", "zxcvb", "zxcvbn",
    "abc", "abcd", "abcde", "abcdef",
    "aaa", "bbb", "ccc", "xxx", "yyy", "zzz",
    "wer", "werd", "wert",
    "fff", "ggg", "ddd", "sss", "aaaa",
    "fake", "n/a", "na", "none", "nobody", "anonymous",
    "lol", "lmao", "kek", "hehe", "haha",
    "ыва", "фыв", "фыва", "ываф", "йцу", "йцук", "йцукен",
})


def _validate_real_identity(data: dict) -> tuple[bool, str | None, str | None]:
    """Reject obviously-fake demo signups.

    Returns (ok, field, message). When ok is False, field names the
    offending input ("firstName" / "lastName" / "email") and message
    is a user-facing string the form should display verbatim.
    Backend is the source of truth — even if a client skips its own
    validation, this gate runs before anything is persisted.
    """
    first = (data.get("firstName") or "").strip()
    last = (data.get("lastName") or "").strip()
    email = (data.get("email") or "").strip().lower()

    # Names: minimum 2 chars each (covers "Li", "Wu", etc. — real),
    # rejects single-letter and empty after trim.
    if len(first) < 2:
        return False, "firstName", "Please enter your real first name."
    if len(last) < 2:
        return False, "lastName", "Please enter your real last name."

    def _is_junk_name(name: str) -> bool:
        lc = name.lower()
        if lc in _JUNK_NAME_LITERALS:
            return True
        # All digits ("123", "12345")
        if lc.isdigit():
            return True
        # All the same character ("aaa", "....", "----")
        if len(set(lc)) == 1 and len(lc) >= 2:
            return True
        # Strip non-letters and check what's left — catches "123 abc"
        letters_only = re.sub(r"[^a-zа-яё]", "", lc)
        if letters_only and letters_only in _JUNK_NAME_LITERALS:
            return True
        return False

    if _is_junk_name(first):
        return False, "firstName", (
            "Please enter your real first name — placeholder values "
            "like \"test\" or \"123\" are not allowed."
        )
    if _is_junk_name(last):
        return False, "lastName", (
            "Please enter your real last name — placeholder values "
            "like \"test\" or \"123\" are not allowed."
        )

    # Email shape: must contain @ and a dot in the domain. The form
    # already does a basic regex but we re-check to be safe.
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        return False, "email", "Please enter a valid email address."
    local, _, domain = email.partition("@")
    domain = domain.strip(".")

    if domain in _DISPOSABLE_EMAIL_DOMAINS:
        return False, "email", (
            "Please use a real email address — disposable and "
            "throwaway addresses are not allowed for demo access."
        )
    # Sub-domain match (e.g. anything.mailinator.com)
    for bad in _DISPOSABLE_EMAIL_DOMAINS:
        if domain.endswith("." + bad):
            return False, "email", (
                "Please use a real email address — disposable and "
                "throwaway addresses are not allowed for demo access."
            )

    for pat in _JUNK_LOCALPART_PATTERNS:
        if pat.match(local):
            return False, "email", (
                "Please use your real email address — placeholder "
                "addresses like \"test@…\" or \"123@…\" are not allowed."
            )

    # All-numeric domain second-level ("123.com", "1.com")
    domain_parts = domain.split(".")
    if domain_parts and domain_parts[0].isdigit():
        return False, "email", (
            "Please enter a valid email address from a real domain."
        )

    return True, None, None

DATA_FILE = "/root/clawd/demo-registrations.jsonl"
TOKENS_FILE = "/root/clawd/demo-tokens.json"
LICENSE_DATA_FILE = "/root/clawd/license-requests.jsonl"
BASE_URL = os.environ.get("BASE_URL", "https://openconstructionerp.com")

TIER_LABELS = {
    "starter": "Starter (on request)",
    "whitelabel": "White-label SaaS (up to 10 tenants)",
    "converters": "DDC cad2data converters",
    "other": "Not sure yet — please advise",
}

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "info@datadrivenconstruction.io")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "OpenConstructionERP <info@datadrivenconstruction.io>")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "info@datadrivenconstruction.io")


def load_tokens():
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def send_email(to, subject, html_body, text_body=""):
    if RESEND_API_KEY:
        return _send_resend(to, subject, html_body)
    if SMTP_HOST:
        return _send_smtp(to, subject, html_body, text_body)
    print("[WARN] No email provider configured", file=sys.stderr)
    return False


def _send_smtp(to, subject, html_body, text_body=""):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [to], msg.as_string())
    return True


def _send_resend(to, subject, html_body):
    data = json.dumps({
        "from": RESEND_FROM, "to": [to], "subject": subject, "html": html_body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=data,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status == 200


def make_license_admin_email(data, ref_id):
    """Internal notification to admin with full lead details."""
    name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
    tier_key = (data.get("tier") or "").lower()
    tier_label = TIER_LABELS.get(tier_key, tier_key or "—")
    ref = data.get("ref") or "(direct)"
    ref_first = data.get("ref_first_seen") or "—"
    utm = " / ".join(
        [
            data.get("utm_source") or "",
            data.get("utm_medium") or "",
            data.get("utm_campaign") or "",
        ]
    ).strip(" /") or "—"
    landing = data.get("landing_page") or "—"
    msg = (data.get("message") or "").strip() or "—"
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#0f172a;">
<h2 style="margin:0 0 4px;font-size:18px;">New commercial licence request</h2>
<p style="color:#64748b;margin:0 0 16px;font-size:13px;">Reference: <strong>{ref_id}</strong></p>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr><td style="padding:6px 0;color:#64748b;width:140px;">Name</td><td style="padding:6px 0;"><strong>{name}</strong></td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Email</td><td style="padding:6px 0;"><a href="mailto:{data.get('email','')}" style="color:#0066ff;">{data.get('email','')}</a></td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Company</td><td style="padding:6px 0;">{data.get('company','')}</td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Country</td><td style="padding:6px 0;">{data.get('country','')}</td></tr>
<tr><td style="padding:6px 0;color:#64748b;">Tier</td><td style="padding:6px 0;"><strong>{tier_label}</strong></td></tr>
<tr><td style="padding:6px 0;color:#64748b;vertical-align:top;">Notes</td><td style="padding:6px 0;white-space:pre-wrap;">{msg}</td></tr>
<tr><td colspan="2" style="padding:14px 0 6px;color:#64748b;font-size:12px;border-top:1px solid #e2e8f0;">Attribution</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Referrer</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{ref}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">First seen</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{ref_first}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">UTM</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{utm}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Landing</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:12px;word-break:break-all;">{landing}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">IP</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{data.get('ip','')}</td></tr>
<tr><td style="padding:4px 0;color:#64748b;">Submitted</td><td style="padding:4px 0;font-family:ui-monospace,monospace;font-size:13px;">{data.get('server_time','')}</td></tr>
</table>
</body></html>'''


def make_license_customer_email(data, ref_id):
    """Acknowledgement to the requester."""
    name = data.get("firstName", "").strip() or "there"
    tier_key = (data.get("tier") or "").lower()
    tier_label = TIER_LABELS.get(tier_key, tier_key or "—")
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#0f172a;">
<div style="text-align:center;margin-bottom:24px;">
<h1 style="font-size:22px;margin:0;">OpenConstructionERP</h1>
<p style="color:#64748b;font-size:14px;margin-top:4px;">Commercial licence request received</p>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;">
<p style="font-size:15px;">Hi {name},</p>
<p style="font-size:15px;">Thanks for your interest in licensing OpenConstructionERP commercially.</p>
<p style="font-size:15px;">We received your request for <strong>{tier_label}</strong> and will reply within <strong>two business days</strong> with a draft agreement and an invoice in EUR.</p>
<p style="font-size:14px;color:#64748b;margin-top:18px;">Reference ID: <span style="font-family:ui-monospace,monospace;background:#fff;padding:3px 8px;border-radius:6px;border:1px solid #e2e8f0;">{ref_id}</span></p>
<p style="font-size:14px;color:#64748b;margin-top:12px;">If anything is urgent, just reply to this email or write to <a href="mailto:info@datadrivenconstruction.io" style="color:#0066ff;">info@datadrivenconstruction.io</a>.</p>
</div>
<div style="text-align:center;margin-top:24px;font-size:12px;color:#94a3b8;">
<p><a href="https://openconstructionerp.com" style="color:#94a3b8;">openconstructionerp.com</a> &middot; DataDrivenConstruction.io &middot; Graben-Neudorf, Germany</p>
</div>
</body></html>'''


def make_confirmation_email(data, verify_url):
    name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="text-align:center;margin-bottom:24px;">
<h1 style="font-size:22px;color:#1a1a1a;margin:0;">OpenConstructionERP</h1>
<p style="color:#666;font-size:14px;margin-top:4px;">Confirm your demo access</p>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;">
<p style="font-size:15px;color:#333;">Hi {name},</p>
<p style="font-size:15px;color:#333;">Thank you for your interest! Please confirm your email to activate demo access:</p>
<div style="text-align:center;margin:24px 0;">
<a href="{verify_url}" style="display:inline-block;background:#2563eb;color:white;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
Activate Demo Access</a>
</div>
<p style="font-size:13px;color:#888;">Or copy: <a href="{verify_url}" style="color:#2563eb;">{verify_url}</a></p>
</div>
<div style="text-align:center;margin-top:24px;font-size:12px;color:#aaa;">
<p><a href="https://openconstructionerp.com" style="color:#888;">openconstructionerp.com</a>
&middot; <a href="mailto:info@datadrivenconstruction.io" style="color:#888;">info@datadrivenconstruction.io</a></p>
</div></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/verify":
            params = urllib.parse.parse_qs(parsed.query)
            token = params.get("token", [""])[0]
            if not token:
                self.send_json(400, {"error": "Missing token"})
                return
            tokens = load_tokens()
            entry = tokens.get(token)
            if not entry:
                self.send_response(302)
                self.send_header("Location", f"{BASE_URL}/demo?error=invalid_token")
                self.end_headers()
                return
            entry["verified"] = True
            entry["verified_at"] = datetime.now(timezone.utc).isoformat()
            save_tokens(tokens)
            # Notify admin
            try:
                admin_text = (
                    f"Verified: {entry.get('firstName','')} {entry.get('lastName','')}\n"
                    f"Email: {entry.get('email','')}\n"
                    f"Company: {entry.get('company','')}\n"
                    f"Role: {entry.get('role','-')}\n"
                    f"IP: {entry.get('ip','')}"
                )
                send_email(ADMIN_EMAIL,
                    f"[Demo] Verified: {entry.get('firstName','')} {entry.get('lastName','')} - {entry.get('company','')}",
                    f"<pre>{admin_text}</pre>", admin_text)
            except Exception as e:
                print(f"[WARN] Admin email failed: {e}", file=sys.stderr)
            print(f"[VERIFIED] {entry.get('email')}")
            self.send_response(302)
            self.send_header("Location", f"{BASE_URL}/demo?verified=true")
            self.end_headers()
        elif parsed.path == "/health":
            self.send_json(200, {"status": "ok", "email": "smtp" if SMTP_HOST else ("resend" if RESEND_API_KEY else "none")})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/license-request":
            self._handle_license_request()
            return
        if self.path != "/register":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return
        for field in ["firstName", "lastName", "email", "company"]:
            if not data.get(field, "").strip():
                self.send_json(400, {
                    "error": f"Missing: {field}",
                    "field": field,
                    "message": "Please fill in all required fields.",
                })
                return
        # Anti-spam gate: reject "test / 123 / asdf" placeholder
        # signups before they hit the data file or the verification
        # email pipeline.
        ok, bad_field, bad_message = _validate_real_identity(data)
        if not ok:
            self.send_json(400, {
                "error": "invalid_identity",
                "field": bad_field,
                "message": bad_message,
            })
            print(
                f"[REJECT] {bad_field}: {data.get(bad_field, '')!r} "
                f"from {self.client_address[0]}",
                file=sys.stderr,
            )
            return
        email = data["email"].strip().lower()
        data["server_time"] = datetime.now(timezone.utc).isoformat()
        data["ip"] = self.client_address[0]
        data["verified"] = False
        token = secrets.token_urlsafe(32)
        verify_url = f"{BASE_URL}/demo-api/verify?token={token}"
        # Save
        try:
            with open(DATA_FILE, "a") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save: {e}", file=sys.stderr)
        tokens = load_tokens()
        tokens[token] = {**data, "token": token}
        save_tokens(tokens)
        # Send confirmation
        email_sent = False
        try:
            html = make_confirmation_email(data, verify_url)
            email_sent = send_email(email, "Confirm your OpenConstructionERP demo access", html)
        except Exception as e:
            print(f"[ERROR] Email: {e}", file=sys.stderr)
        if email_sent:
            self.send_json(200, {"status": "confirmation_sent"})
            print(f"[REG] Confirmation -> {email}")
        else:
            # Fallback: auto-verify
            tokens[token]["verified"] = True
            save_tokens(tokens)
            self.send_json(200, {"status": "ok"})
            print(f"[REG] Auto-verified (no email): {email}")

    def _handle_license_request(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        # Required fields (mirrors the form). Country and tier are
        # licence-specific compared with the demo registration flow.
        required = ["firstName", "lastName", "email", "company", "country", "tier"]
        for field in required:
            if not (data.get(field) or "").strip():
                self.send_json(400, {
                    "error": f"Missing: {field}",
                    "field": field,
                    "message": "Please fill in all required fields.",
                })
                return

        if data["tier"] not in TIER_LABELS:
            self.send_json(400, {
                "error": "invalid_tier",
                "field": "tier",
                "message": "Please select a valid licence tier.",
            })
            return

        # Same anti-spam gate as demo signups — junk names and
        # disposable email domains are blocked before we persist
        # anything or fire emails.
        ok, bad_field, bad_message = _validate_real_identity(data)
        if not ok:
            self.send_json(400, {
                "error": "invalid_identity",
                "field": bad_field,
                "message": bad_message,
            })
            print(
                f"[LIC-REJECT] {bad_field}: {data.get(bad_field, '')!r} "
                f"from {self.client_address[0]}",
                file=sys.stderr,
            )
            return

        # Reference ID — short, monotonic-ish, easy to quote on the
        # phone. Same shape Kristijan/partners will see in their
        # affiliate dashboard later.
        ref_id = "OCERP-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

        data["email"] = data["email"].strip().lower()
        data["server_time"] = datetime.now(timezone.utc).isoformat()
        data["ip"] = self.client_address[0]
        data["reference_id"] = ref_id
        data["kind"] = "license_request"

        # Persist before sending mail — if SMTP/Resend fails we
        # still have the lead. JSONL append, one row per request.
        try:
            with open(LICENSE_DATA_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ERROR] Save license request: {e}", file=sys.stderr)

        # Admin notification — full lead + attribution. We deliberately
        # don't fail the request when email delivery fails; the JSONL
        # is the source of truth and the form already returned success.
        try:
            admin_html = make_license_admin_email(data, ref_id)
            admin_subject = (
                f"[Licence] {data.get('tier','?')} · "
                f"{data.get('company','')} · "
                f"{data.get('firstName','')} {data.get('lastName','')}"
            )
            send_email(ADMIN_EMAIL, admin_subject, admin_html)
        except Exception as e:
            print(f"[WARN] Admin license email failed: {e}", file=sys.stderr)

        # Customer acknowledgement. Best-effort: any failure here is
        # logged but doesn't affect the user-facing success state.
        try:
            customer_html = make_license_customer_email(data, ref_id)
            send_email(
                data["email"],
                "Your OpenConstructionERP commercial licence request",
                customer_html,
            )
        except Exception as e:
            print(f"[WARN] Customer license email failed: {e}", file=sys.stderr)

        print(
            f"[LIC] {ref_id} tier={data.get('tier')} "
            f"company={data.get('company')!r} ref={data.get('ref') or '-'}"
        )
        self.send_json(200, {"status": "received", "reference_id": ref_id})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Demo registration API v2 (email verification) on port {PORT}")
    print(f"  Email: {'SMTP' if SMTP_HOST else ('Resend' if RESEND_API_KEY else 'NONE (auto-verify)')}")
    print(f"  Admin: {ADMIN_EMAIL}")
    server.serve_forever()
