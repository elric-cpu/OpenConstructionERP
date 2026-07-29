#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base_url: str, path: str) -> tuple[int, str, bytes]:
    target = f"{base_url.rstrip('/')}{path}"
    try:
        with urlopen(
            Request(target, headers={"User-Agent": "benson-release-smoke/1"}), timeout=60
        ) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except URLError as exc:
        raise RuntimeError(f"request failed for {target}: {exc.reason}") from exc


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def json_body(body: bytes, path: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} did not return JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} did not return a JSON object")
    return value


def smoke(base_url: str, expected_email_backend: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    status, content_type, body = request(base_url, "/api/health")
    health = json_body(body, "/api/health") if status == 200 else {}
    add_check(checks, "health", status == 200 and health.get("status") == "healthy", health)
    add_check(checks, "database", health.get("database") == "ok", health.get("database"))
    add_check(
        checks,
        "module_inventory",
        int(health.get("modules_loaded", 0)) >= 183,
        health.get("modules_loaded"),
    )
    add_check(checks, "health_content_type", "application/json" in content_type, content_type)

    status, _, body = request(base_url, "/api/v1/benson-edition/")
    edition = json_body(body, "/api/v1/benson-edition/") if status == 200 else {}
    providers = edition.get("providers", {}) if isinstance(edition.get("providers"), dict) else {}
    resend = providers.get("resend", {}) if isinstance(providers.get("resend"), dict) else {}
    directory = (
        providers.get("google_directory", {})
        if isinstance(providers.get("google_directory"), dict)
        else {}
    )
    add_check(
        checks, "benson_edition", status == 200 and edition.get("edition") == "benson", edition
    )
    add_check(
        checks,
        "english_only",
        edition.get("supported_locales") == ["en"],
        edition.get("supported_locales"),
    )
    add_check(
        checks,
        "eastern_oregon",
        edition.get("default_region") == "benson_eastern_oregon",
        edition.get("default_region"),
    )
    add_check(
        checks,
        "resend_state",
        bool(resend.get("enabled")) == (expected_email_backend == "resend"),
        resend,
    )
    add_check(checks, "directory_disabled", directory.get("enabled") is False, directory)

    for path in ("/benson", "/projects/example"):
        status, content_type, body = request(base_url, path)
        add_check(
            checks,
            f"spa:{path}",
            status == 200 and "text/html" in content_type and b"<html" in body.lower(),
            {"status": status, "content_type": content_type},
        )

    for path in (
        "/api/does-not-exist",
        "/health/does-not-exist",
        "/metrics/does-not-exist",
        "/api/openapi.json",
    ):
        status, content_type, _ = request(base_url, path)
        add_check(
            checks,
            f"reserved_404:{path}",
            status == 404 and "text/html" not in content_type,
            {"status": status, "content_type": content_type},
        )

    passed = all(check["passed"] for check in checks)
    return {
        "status": "pass" if passed else "fail",
        "base_url": base_url,
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test a zero-traffic Benson Cloud Run candidate."
    )
    parser.add_argument("base_url")
    parser.add_argument("--expected-email-backend", choices=("noop", "resend"), default="noop")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = smoke(args.base_url, args.expected_email_backend)
    except RuntimeError as exc:
        report = {
            "status": "fail",
            "base_url": args.base_url,
            "checked_at": datetime.now(UTC).isoformat(),
            "error": str(exc),
            "checks": [],
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
