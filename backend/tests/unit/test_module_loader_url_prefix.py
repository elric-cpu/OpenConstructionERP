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
# routes. Each test below therefore boots the loader in a brand-new interpreter,
# which removes the whole class of cross-test import contamination and exercises
# the loader the way the app actually starts. The probe carries diagnostics so a
# failure self-explains in the CI log.

from __future__ import annotations

import json
import subprocess
import sys

# Program run in a fresh interpreter. It boots the real ModuleLoader, mounts one
# module onto a throwaway FastAPI app, and prints a diagnostics blob as JSON on a
# marked line. It only imports and mounts routes (no DB connection is made), so
# it does not need the test database.
_LOADER_PROBE = """\
import sys, os, json, traceback, importlib, logging

module_name = sys.argv[1]
dir_name = module_name[3:] if module_name.startswith("oe_") else module_name
warns = []


class _Collect(logging.Handler):
    def emit(self, record):
        try:
            warns.append(self.format(record))
        except Exception:
            pass


logging.getLogger().addHandler(_Collect())
logging.getLogger().setLevel(logging.WARNING)

diag = {"py": sys.version.split()[0], "cwd": os.getcwd(), "syspath": sys.path[:4]}

try:
    rm = importlib.import_module("app.modules." + dir_name + ".router")
    diag["router_import"] = "ok"
    diag["router_routes"] = len(getattr(getattr(rm, "router", None), "routes", []) or [])
except Exception as exc:
    diag["router_import"] = repr(exc)
    diag["router_tb"] = traceback.format_exc()[-1500:]

try:
    import asyncio
    from fastapi import FastAPI
    from app.core.module_loader import ModuleLoader

    loader = ModuleLoader()
    loader.discover()
    diag["manifest_count"] = len(getattr(loader, "_manifests", {}))
    diag["in_manifests"] = module_name in getattr(loader, "_manifests", {})
    app = FastAPI()
    asyncio.run(loader._load_module(module_name, app))
    all_paths = sorted({getattr(route, "path", "") for route in app.routes})
    kebab = "/api/v1/" + dir_name.replace("_", "-") + "/"
    under = "/api/v1/" + dir_name + "/"
    diag["mounted_count"] = len(all_paths)
    diag["kebab_paths"] = [p for p in all_paths if p.startswith(kebab)]
    diag["under_paths"] = [p for p in all_paths if p.startswith(under)]
except Exception as exc:
    diag["loader_error"] = repr(exc)
    diag["loader_tb"] = traceback.format_exc()[-1500:]

diag["warns"] = warns[-6:]
sys.stdout.write("OE_DIAG=" + json.dumps(diag) + "\\n")
"""


def _probe(module_name: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _LOADER_PROBE, module_name],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    marker = "OE_DIAG="
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(marker)), None)
    assert line is not None, (
        f"loader probe for {module_name} produced no diagnostics (exit {proc.returncode}).\n"
        f"stdout tail:\n{proc.stdout[-2000:]}\nstderr tail:\n{proc.stderr[-2500:]}"
    )
    return json.loads(line[len(marker) :])


def test_bi_dashboards_mounted_on_kebab_case() -> None:
    """``bi_dashboards`` package must serve under ``/api/v1/bi-dashboards``."""
    diag = _probe("oe_bi_dashboards")
    paths = diag.get("kebab_paths") or []
    assert paths, (
        "BI dashboards router must mount under /api/v1/bi-dashboards/* "
        f"(frontend api.ts uses this kebab-case prefix). diag={json.dumps(diag)[:3500]}"
    )
    assert any(p == "/api/v1/bi-dashboards/dashboards" for p in paths), (
        f"Missing POST /api/v1/bi-dashboards/dashboards: {paths!r}"
    )


def test_bi_dashboards_legacy_underscore_mirror() -> None:
    """The underscore form is mirrored for callers that haven't migrated."""
    diag = _probe("oe_bi_dashboards")
    paths = diag.get("under_paths") or []
    assert paths, (
        "Legacy /api/v1/bi_dashboards mirror is missing - third-party "
        f"callers that have not migrated to the kebab-case URL would 404. diag={json.dumps(diag)[:3500]}"
    )


def test_hse_advanced_mounted_on_kebab_case() -> None:
    """``hse_advanced`` package must serve under ``/api/v1/hse-advanced``."""
    diag = _probe("oe_hse_advanced")
    paths = diag.get("kebab_paths") or []
    assert paths, f"hse-advanced did not mount. diag={json.dumps(diag)[:3500]}"
    assert any(p == "/api/v1/hse-advanced/investigations/" for p in paths), (
        f"Missing GET /api/v1/hse-advanced/investigations/: {paths!r}"
    )


def test_schedule_advanced_mounted_on_kebab_case() -> None:
    """``schedule_advanced`` package must serve under ``/api/v1/schedule-advanced``.

    The user's "create doesn't work" on /schedule-advanced was caused by this
    URL mismatch.
    """
    diag = _probe("oe_schedule_advanced")
    paths = diag.get("kebab_paths") or []
    assert paths, f"schedule-advanced did not mount. diag={json.dumps(diag)[:3500]}"
    assert any(p == "/api/v1/schedule-advanced/master-schedules/" for p in paths), (
        f"Missing POST /api/v1/schedule-advanced/master-schedules/: {paths!r}"
    )
