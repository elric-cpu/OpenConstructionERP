# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
#
# Regression test for the module-loader URL-prefix derivation.
#
# Background: the recently-added 18 modules were shipped with frontend
# api.ts files that hit hyphenated paths like ``/api/v1/bi-dashboards``
# and ``/api/v1/hse-advanced``. The loader, however, derived the URL
# prefix straight from the Python package directory name (which uses
# underscores), so the frontend got a 404 on every request and the
# user reported pages like /bi-dashboards and /hse-advanced as "не
# работает полностью" (completely broken).
#
# The fix mounts the router on the kebab-cased path AND mirrors it
# under the legacy underscore form for backward compatibility. This
# test pins both behaviours against the real on-disk ``bi_dashboards``
# and ``hse_advanced`` modules so a future loader refactor cannot
# silently regress the public URL surface.
#
# Isolation note (why a subprocess): ``_load_module`` mounts
# ``app.modules.<dir>.router.router`` straight from ``sys.modules`` and never
# rebuilds it, which is correct for production where every module is imported
# exactly once at startup. Under ``pytest-split`` a different slice of the unit
# suite lands in each shard, and an unrelated earlier test in the same worker
# could leave one of these router modules cached in a state that mounts zero
# routes. In-process cures (reload, pop-and-reimport) could not be made reliable
# across every shard ordering. Each test below therefore boots the loader in a
# brand-new interpreter, which removes the whole class of cross-test import
# contamination and exercises the loader the way the app actually starts.

from __future__ import annotations

import json
import subprocess
import sys

# Program run in a fresh interpreter. It boots the real ModuleLoader, mounts one
# module onto a throwaway FastAPI app, and prints the mounted paths as JSON on a
# marked line. It only imports and mounts routes (no DB connection is made), so
# it does not need the test database.
_LOADER_PROBE = """\
import asyncio
import json
import sys

from fastapi import FastAPI

from app.core.module_loader import ModuleLoader

module_name = sys.argv[1]
loader = ModuleLoader()
loader.discover()
app = FastAPI()
asyncio.run(loader._load_module(module_name, app))
paths = sorted({getattr(route, "path", "") for route in app.routes})
sys.stdout.write("OE_MOUNTED_PATHS=" + json.dumps(paths) + "\\n")
"""


def _mounted_paths(module_name: str, prefix: str) -> list[str]:
    """Mount one real module in a fresh interpreter; return its paths under ``prefix``."""
    proc = subprocess.run(
        [sys.executable, "-c", _LOADER_PROBE, module_name],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, (
        f"loader probe for {module_name} exited {proc.returncode}.\nstderr tail:\n{proc.stderr[-3000:]}"
    )
    marker = "OE_MOUNTED_PATHS="
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(marker)), None)
    assert line is not None, (
        f"loader probe for {module_name} emitted no paths.\n"
        f"stdout tail:\n{proc.stdout[-3000:]}\nstderr tail:\n{proc.stderr[-1500:]}"
    )
    all_paths: list[str] = json.loads(line[len(marker) :])
    return [p for p in all_paths if p.startswith(prefix)]


def test_bi_dashboards_mounted_on_kebab_case() -> None:
    """``bi_dashboards`` package must serve under ``/api/v1/bi-dashboards``."""
    paths = _mounted_paths("oe_bi_dashboards", "/api/v1/bi-dashboards/")
    assert paths, (
        "BI dashboards router must mount under /api/v1/bi-dashboards/* (frontend api.ts uses this kebab-case prefix)."
    )
    # Specifically the create endpoint that was failing for the user.
    assert any(p == "/api/v1/bi-dashboards/dashboards" for p in paths), (
        f"Missing POST /api/v1/bi-dashboards/dashboards: {paths!r}"
    )


def test_bi_dashboards_legacy_underscore_mirror() -> None:
    """The underscore form is mirrored for callers that haven't migrated."""
    paths = _mounted_paths("oe_bi_dashboards", "/api/v1/bi_dashboards/")
    assert paths, (
        "Legacy /api/v1/bi_dashboards mirror is missing - third-party "
        "callers that have not migrated to the kebab-case URL would 404."
    )


def test_hse_advanced_mounted_on_kebab_case() -> None:
    """``hse_advanced`` package must serve under ``/api/v1/hse-advanced``."""
    paths = _mounted_paths("oe_hse_advanced", "/api/v1/hse-advanced/")
    assert paths, paths
    # Investigations list endpoint added during the same fix.
    assert any(p == "/api/v1/hse-advanced/investigations/" for p in paths), (
        f"Missing GET /api/v1/hse-advanced/investigations/: {paths!r}"
    )


def test_schedule_advanced_mounted_on_kebab_case() -> None:
    """``schedule_advanced`` package must serve under
    ``/api/v1/schedule-advanced``. The user's "create doesn't work"
    on /schedule-advanced was caused by this URL mismatch.
    """
    paths = _mounted_paths("oe_schedule_advanced", "/api/v1/schedule-advanced/")
    assert paths, paths
    assert any(p == "/api/v1/schedule-advanced/master-schedules/" for p in paths), (
        f"Missing POST /api/v1/schedule-advanced/master-schedules/: {paths!r}"
    )
