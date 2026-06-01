"""‌⁠‍OpenConstructionERP CLI — run the platform from the command line.

The happy path for a new user is two commands:

    pip install openconstructionerp
    openconstructionerp

The bare ``openconstructionerp`` command creates the local database,
loads the demo data, starts the server and opens the browser. The
explicit subcommands are still there for advanced use:

    openconstructionerp serve   [--host HOST] [--port PORT] [--data-dir DIR] [--open]
    openconstructionerp init-db [--data-dir DIR]
    openconstructionerp doctor  [--host HOST] [--port PORT] [--data-dir DIR]
    openconstructionerp seed    [--demo] [--data-dir DIR]
    openconstructionerp version

``openconstructionerp doctor`` runs pre-flight checks and prints OK /
WARNING / ERROR per check so you can diagnose install problems.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import webbrowser
from pathlib import Path

# ── Console encoding hardening ────────────────────────────────────────────
# On Windows + Anaconda Python the default console encoding is cp1252,
# which crashes on any non-ASCII character (em-dash, arrow, box-drawing,
# etc.). This is the same family of bug that killed v1.3.9 — silent or
# noisy failure on Windows. We try to switch stdout/stderr to UTF-8 if
# possible; otherwise we fall back to ASCII-only output.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _stdout_supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


DEFAULT_DATA_DIR = Path.home() / ".openestimate"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
MIN_PYTHON = (3, 12)

DOCS_URL = "https://openconstructionerp.com/docs"
TROUBLESHOOTING_URL = "https://openconstructionerp.com/docs#troubleshooting"
ISSUES_URL = "https://github.com/datadrivenconstruction/OpenConstructionERP/issues"
COMMUNITY_URL = "https://t.me/datadrivenconstruction"
GITHUB_URL = "https://github.com/datadrivenconstruction/OpenConstructionERP"

logger = logging.getLogger("openestimate.cli")


# ── ANSI colors (amber accent #f0883e, disabled if no TTY or NO_COLOR) ────
def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    # Windows: modern Terminal / PowerShell / Git Bash handle ANSI fine.
    # Legacy cmd.exe does not, but colorama is already a uvicorn transitive
    # dep on Windows, so we can enable it opportunistically.
    if sys.platform == "win32":
        try:
            import colorama

            colorama.just_fix_windows_console()
        except Exception:
            return False
    return True


_COLOR = _supports_color()
_UNICODE = _stdout_supports_unicode()


def _u(unicode_str: str, ascii_fallback: str) -> str:
    """‌⁠‍Pick the unicode form when the console can render it, else ASCII."""
    return unicode_str if _UNICODE else ascii_fallback


def _c(text: str, code: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _amber(text: str) -> str:
    # 256-color approximation of the project accent #f0883e
    return _c(text, "38;5;208")


def _green(text: str) -> str:
    return _c(text, "32")


def _red(text: str) -> str:
    return _c(text, "31")


def _yellow(text: str) -> str:
    return _c(text, "33")


def _dim(text: str) -> str:
    return _c(text, "2")


def _bold(text: str) -> str:
    return _c(text, "1")


def _bar() -> str:
    """Left accent rule for the info panels (amber bar, ASCII pipe fallback)."""
    return _amber(_u("┃", "|"))


# ── Banner ────────────────────────────────────────────────────────────────
# "OpenConstructionERP" rendered in the figlet "small" font (82 cols × 5
# rows). The previous "Standard" font wrapped the 19-character name onto
# multiple visual rows on a typical 80-col terminal, which looked crooked;
# the "small" font fits the full name on one row with the trailing "ERP"
# inline. Generated once with pyfiglet and pasted in — no runtime dep.
_BANNER_ART = r"""  ___                 ___             _               _   _          ___ ___ ___
 / _ \ _ __  ___ _ _ / __|___ _ _  __| |_ _ _ _  _ __| |_(_)___ _ _ | __| _ \ _ \
| (_) | '_ \/ -_) ' \ (__/ _ \ ' \(_-<  _| '_| || / _|  _| / _ \ ' \| _||   /  _/
 \___/| .__/\___|_||_\___\___/_||_/__/\__|_|  \_,_\__|\__|_\___/_||_|___|_|_\_|
      |_|"""


def print_startup_banner(
    version: str,
    host: str,
    port: int,
    data_dir: Path,
    *,
    serve_frontend: bool,
) -> None:
    """Print a friendly multi-line startup banner.

    Shown after the server has bound its socket and is ready to accept
    connections. Designed to be scanned in under three seconds: what URL
    to open, how to log in, where the data lives, how to stop.
    """
    url = f"http://{host}:{port}"
    bar = _bar()
    check = _green(_u("✔", "OK"))
    print()
    print(_amber(_BANNER_ART))
    print()
    print(f"  {bar}  {check} {_bold('OpenConstructionERP is running')}  {_dim('v' + version)}")
    print(f"  {bar}")
    print(f"  {bar}  {_bold('Open in your browser')}")
    print(f"  {bar}     {_amber(url)}")
    if serve_frontend:
        print(f"  {bar}     {_dim(url + '/api/docs   (API reference)')}")
    else:
        print(f"  {bar}     {_dim('frontend not bundled, API only at ' + url + '/api/docs')}")
    print(f"  {bar}")
    print(f"  {bar}  {_bold('Log in with the demo account')}")
    print(f"  {bar}     demo@openconstructionerp.com  {_dim('/')}  DemoPass1234!")
    print(f"  {bar}")
    print(f"  {bar}  {_dim('Stop'.ljust(11))} Ctrl+C")
    print(f"  {bar}  {_dim('Start again'.ljust(11))} {_amber('openconstructionerp')}")
    print(f"  {bar}  {_dim('Data folder'.ljust(11))} {data_dir}")
    print(f"  {bar}  {_dim('Need help'.ljust(11))} {DOCS_URL}")
    print()


# ── Environment setup ─────────────────────────────────────────────────────
def _setup_env(data_dir: Path, host: str, port: int) -> None:
    """Configure environment variables for local-first operation.

    All settings use ``setdefault`` so the user can still override via
    a real environment variable or a .env file.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "vectors").mkdir(exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)

    db_path = data_dir / "openestimate.db"

    # Embedded PostgreSQL (no Docker) is the DEFAULT runtime as of v6.0.0: boot a
    # real in-process PG16 and point DATABASE_URL/DATABASE_SYNC_URL at it BEFORE
    # the SQLite setdefault below (which then no-ops because the keys are already
    # set). Opt out with OE_USE_SQLITE=1 (legacy single-file SQLite) or by setting
    # your own DATABASE_URL. Must run before any ``from app...`` import that builds
    # the engine — _setup_env is that earliest point for every command.
    from app.core import embedded_pg

    if embedded_pg.is_requested():
        if embedded_pg.boot(data_dir):
            # Transparent one-time SQLite -> PostgreSQL migration: if the box has
            # a legacy openestimate.db and the embedded cluster is still empty,
            # move the data over before the server starts. No-op otherwise.
            status = embedded_pg.auto_migrate_legacy_sqlite(data_dir)
            if status.startswith("migrated"):
                print(_green(_u("✓ ", "OK ")) + status)
            print(_green(_u("✓ ", "OK ")) + "Database: embedded PostgreSQL 16 (no Docker)")
        else:
            # pixeltable-pgserver missing or initdb failed: degrade to SQLite so
            # the app still comes up. Surface it so the operator can install the
            # server extra or set DATABASE_URL.
            print(
                _yellow(_u("⚠ ", "! "))
                + "Embedded PostgreSQL unavailable; falling back to SQLite. "
                + "Install with 'pip install openconstructionerp[server]' or set OE_USE_SQLITE=1 to silence."
            )

    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    os.environ.setdefault("DATABASE_SYNC_URL", f"sqlite:///{db_path}")
    os.environ.setdefault("VECTOR_BACKEND", "lancedb")
    os.environ.setdefault("VECTOR_DATA_DIR", str(data_dir / "vectors"))
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_DEBUG", "false")
    os.environ.setdefault("ALLOWED_ORIGINS", f"http://{host}:{port}")
    os.environ.setdefault("JWT_SECRET", "openestimate-local-dev-key")

    # Desktop / CLI mode: serve frontend from the wheel
    os.environ["SERVE_FRONTEND"] = "true"

    # Publish the ready banner info so main.py can pick it up after the
    # uvicorn socket is actually bound (see core/startup_banner.py).
    os.environ["OE_CLI_HOST"] = host
    os.environ["OE_CLI_PORT"] = str(port)
    os.environ["OE_CLI_DATA_DIR"] = str(data_dir)


# ── Pre-flight checks ─────────────────────────────────────────────────────
class Check:
    """A single doctor check result."""

    def __init__(self, name: str, status: str, message: str, hint: str = "") -> None:
        self.name = name
        self.status = status  # "ok" | "warn" | "error"
        self.message = message
        self.hint = hint

    def print(self) -> None:
        badge = {
            "ok": _green("  OK   "),
            "warn": _yellow(" WARN  "),
            "error": _red(" ERROR "),
        }.get(self.status, self.status)
        print(f"  [{badge}] {self.name}: {self.message}")
        if self.hint and self.status != "ok":
            arrow = _u("\u2192 ", "-> ")
            print(f"            {_dim(arrow + self.hint)}")


def check_python_version() -> Check:
    ver = sys.version_info
    if (ver.major, ver.minor) < MIN_PYTHON:
        return Check(
            "Python version",
            "error",
            f"Python {ver.major}.{ver.minor} is too old (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)",
            f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ from python.org and reinstall the package",
        )
    return Check(
        "Python version",
        "ok",
        f"Python {ver.major}.{ver.minor}.{ver.micro}",
    )


def check_package_installed() -> Check:
    try:
        from importlib.metadata import version as _v

        v = _v("openconstructionerp")
        return Check("Package installed", "ok", f"openconstructionerp v{v}")
    except Exception:
        return Check(
            "Package installed",
            "warn",
            "running from source checkout (not pip-installed)",
            "For production use: pip install openconstructionerp",
        )


def check_data_dir(data_dir: Path) -> Check:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".writetest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("Data directory", "ok", f"writable at {data_dir}")
    except Exception as exc:
        return Check(
            "Data directory",
            "error",
            f"cannot write to {data_dir}: {exc}",
            f"Use --data-dir to pick a writable path, e.g. --data-dir {Path.home() / 'openestimate-data'}",
        )


def check_port_free(host: str, port: int) -> Check:
    """Verify nothing is already listening on the requested port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            # Linux/macOS: bind fails if port is in use.
            # Windows: connect succeeds if something is already listening.
            if sys.platform == "win32":
                try:
                    sock.connect((host, port))
                    # Connection succeeded → port is in use.
                    return Check(
                        "Port available",
                        "error",
                        f"port {port} on {host} is already in use",
                        f"Stop the other process or use --port {port + 1}",
                    )
                except (OSError, ConnectionRefusedError):
                    pass
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind((host, port))
                except OSError as exc:
                    return Check(
                        "Port available",
                        "error",
                        f"port {port} on {host} is already in use ({exc})",
                        f"Stop the other process or use --port {port + 1}",
                    )
        return Check("Port available", "ok", f"port {port} is free")
    except Exception as exc:
        return Check("Port available", "warn", f"could not check port {port}: {exc}")


def check_frontend_bundled() -> Check:
    pkg_dir = Path(__file__).parent / "_frontend_dist"
    if pkg_dir.is_dir() and (pkg_dir / "index.html").exists():
        return Check("Frontend bundle", "ok", "bundled React UI ready")
    dev_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dev_dist.is_dir() and (dev_dist / "index.html").exists():
        return Check("Frontend bundle", "ok", f"using dev build from {dev_dist}")
    return Check(
        "Frontend bundle",
        "warn",
        "no frontend found — server will run API only",
        "Reinstall the pip package to get the bundled UI, or run `npm run build` in frontend/",
    )


def check_env_overrides() -> Check:
    """Warn if DATABASE_URL / JWT_SECRET look wrong."""
    db = os.environ.get("DATABASE_URL", "")
    if db and not (db.startswith("sqlite") or db.startswith("postgresql")):
        return Check(
            "DATABASE_URL",
            "warn",
            f"unrecognised scheme: {db.split(':', 1)[0]}",
            "Use sqlite+aiosqlite:///... or postgresql+asyncpg://...",
        )
    if db.startswith("postgresql"):
        return Check("DATABASE_URL", "ok", "PostgreSQL mode")
    return Check("DATABASE_URL", "ok", "SQLite mode (default)")


def check_core_tabular_deps() -> list[Check]:
    """Verify base tabular dependencies are importable.

    `pandas` and `pyarrow` were promoted from the `[vector]` extra into
    base dependencies in v1.3.13 after a fresh-install bug where the
    CWICR cost-database loader returned HTTP 500 with "No module named
    'pandas'". They are needed by:
      - the `load-cwicr` headline quickstart endpoint
      - the BIM Excel parser (openpyxl + pandas)
      - parquet seed data for classifications & cost databases

    A missing install here is a hard ERROR, not a warning — the app
    will boot but the first onboarding step will 500.
    """
    from importlib.util import find_spec

    hint = "Cost database import requires pandas + pyarrow. Reinstall with: pip install --upgrade openconstructionerp"
    out: list[Check] = []
    for mod in ("pandas", "pyarrow"):
        try:
            present = find_spec(mod) is not None
        except Exception:
            present = False
        if present:
            out.append(Check(f"Tabular core ({mod})", "ok", f"{mod} installed"))
        else:
            out.append(
                Check(
                    f"Tabular core ({mod})",
                    "error",
                    f"{mod} is missing from base dependencies",
                    hint,
                )
            )
    return out


def check_ai_provider_keys() -> Check:
    """Check whether at least one LLM provider API key is configured.

    We call LLM providers via REST (httpx), not vendor SDKs, so there is
    no Python package to probe. Instead, look at the two places keys can
    live:
      1. Settings / environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...)
      2. ``~/.openestimate/config.json`` (CLI-managed overrides)

    This only reports INFO-level WARN when none are set — AI is optional.
    """
    # 1. Settings-level keys (env vars, .env file, pydantic-settings).
    env_key_names = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
    )
    configured = [name for name in env_key_names if os.environ.get(name)]

    # 2. CLI config file overrides.
    config_path = DEFAULT_DATA_DIR / "config.json"
    if config_path.exists():
        try:
            import json

            with open(config_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict):
                for key, val in cfg.items():
                    if key.lower().endswith("_api_key") and val:
                        configured.append(key.upper())
        except Exception:
            pass

    if configured:
        names = ", ".join(sorted({c.split("_")[0].title() for c in configured}))
        return Check(
            "AI provider keys",
            "ok",
            f"configured: {names}",
        )
    return Check(
        "AI provider keys",
        "warn",
        "no LLM provider API key found (AI estimation will be disabled)",
        "Set e.g. ANTHROPIC_API_KEY or OPENAI_API_KEY, or configure via Settings > AI in the UI",
    )


def check_optional_extras() -> list[Check]:
    """Report which optional extras are installed (mostly non-fatal)."""
    from importlib.util import find_spec

    def _present(mod: str) -> bool:
        try:
            return find_spec(mod) is not None
        except Exception:
            return False

    out: list[Check] = []

    # Embedded vector search (LanceDB) — used by the local semantic search
    # path for cost-database matching. Optional: code falls back to keyword
    # match when missing.
    if _present("lancedb"):
        out.append(Check("Vector search [vector]", "ok", "lancedb installed"))
    else:
        out.append(
            Check(
                "Vector search [vector]",
                "warn",
                "not installed (LanceDB semantic search disabled)",
                "pip install 'openconstructionerp[vector]'",
            )
        )

    # Semantic embeddings (sentence-transformers + Qdrant client).
    # Renamed from `[ai]` in v1.3.14 — the old extra is still an alias.
    if _present("sentence_transformers"):
        out.append(Check("Semantic search [semantic]", "ok", "sentence-transformers installed"))
    else:
        out.append(
            Check(
                "Semantic search [semantic]",
                "warn",
                "not installed (RAG / embedding search disabled)",
                "pip install 'openconstructionerp[semantic]'",
            )
        )

    # PDF parsing for takeoff / document extraction.
    if _present("pymupdf") or _present("fitz"):
        out.append(Check("PDF takeoff [cv]", "ok", "pymupdf installed"))
    else:
        out.append(
            Check(
                "PDF takeoff [cv]",
                "warn",
                "not installed (PDF takeoff disabled)",
                "pip install 'openconstructionerp[cv]'",
            )
        )

    # AI provider key configuration (not a package check).
    out.append(check_ai_provider_keys())

    return out


def run_preflight(
    host: str,
    port: int,
    data_dir: Path,
    *,
    verbose: bool = True,
) -> list[Check]:
    """Run the core preflight checks and return the list."""
    checks: list[Check] = [
        check_python_version(),
        check_package_installed(),
        check_data_dir(data_dir),
        check_port_free(host, port),
        check_frontend_bundled(),
        check_env_overrides(),
    ]
    # Base tabular deps (pandas, pyarrow) are ERROR-level: the onboarding
    # load-cwicr endpoint hard-requires them. Run on every preflight so
    # `serve` also catches a broken install before uvicorn spins up.
    checks.extend(check_core_tabular_deps())
    if verbose:
        checks.extend(check_optional_extras())
    return checks


# ── Commands ──────────────────────────────────────────────────────────────
def cmd_serve(args: argparse.Namespace) -> None:
    """Start the OpenConstructionERP server."""
    data_dir = Path(args.data_dir).expanduser().resolve()
    _setup_env(data_dir, args.host, args.port)

    # Run only the fatal preflight checks before attempting to start.
    # If a check fails hard, we stop here with a readable message instead
    # of letting uvicorn crash with a stack trace.
    fatal_checks = [
        check_python_version(),
        check_data_dir(data_dir),
        check_port_free(args.host, args.port),
        *check_core_tabular_deps(),
    ]
    blocking = [c for c in fatal_checks if c.status == "error"]
    if blocking:
        print(
            _red(
                _bold(
                    _u(
                        "Cannot start OpenConstructionERP \u2014 pre-flight checks failed:",
                        "Cannot start OpenConstructionERP - pre-flight checks failed:",
                    )
                )
            )
        )
        print()
        for c in fatal_checks:
            c.print()
        print()
        print(_dim("Run 'openconstructionerp doctor' for full diagnostics."))
        print(_dim(f"Troubleshooting: {TROUBLESHOOTING_URL}"))
        sys.exit(1)

    try:
        from app.config import get_settings

        settings = get_settings()
        version = settings.app_version
    except Exception as exc:
        print(_red(f"Failed to load settings: {exc}"))
        print(_dim(f"Troubleshooting: {TROUBLESHOOTING_URL}"))
        sys.exit(1)

    # Print the banner BEFORE uvicorn starts so the user sees it immediately
    # even if module discovery takes a few seconds.
    if not args.quiet:
        print_startup_banner(
            version=version,
            host=args.host,
            port=args.port,
            data_dir=data_dir,
            serve_frontend=True,
        )
        print(
            _dim(
                _u(
                    "  Starting server… first run may take up to 30 seconds.",
                    "  Starting server... first run may take up to 30 seconds.",
                )
            )
        )
        print()

    if args.open:
        import threading
        import time

        def _open_browser() -> None:
            time.sleep(3)
            try:
                webbrowser.open(f"http://{args.host}:{args.port}")
            except Exception:
                pass

        threading.Thread(target=_open_browser, daemon=True).start()

    try:
        import uvicorn

        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            log_level="warning" if args.quiet else "info",
            access_log=False,
        )
    except KeyboardInterrupt:
        print()
        print(_dim("Server stopped. Bye!"))
    except OSError as exc:
        print()
        print(_red(_bold("Server failed to start:")) + f" {exc}")
        arrow = _u("\u2192", "->")
        if "address already in use" in str(exc).lower() or "10048" in str(exc):
            print(_dim(f"  {arrow} Port {args.port} is already in use. Try: openconstructionerp serve --port {args.port + 1}"))
        else:
            print(_dim(f"  {arrow} See: {TROUBLESHOOTING_URL}"))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        arrow = _u("\u2192", "->")
        print()
        print(_red(_bold("Unexpected startup error:")) + f" {type(exc).__name__}: {exc}")
        print(_dim(f"  {arrow} Run 'openconstructionerp doctor' to diagnose."))
        print(_dim(f"  {arrow} Report this at: {ISSUES_URL}"))
        sys.exit(1)


def cmd_init_db(args: argparse.Namespace) -> None:
    """Initialise data directory and create the SQLite database."""
    data_dir = Path(args.data_dir).expanduser().resolve()
    db_path = data_dir / "openestimate.db"
    reset = bool(getattr(args, "reset", False))

    # Honour --reset BEFORE _setup_env touches the directory so the user
    # gets a guaranteed-fresh DB. We also wipe the SQLite WAL siblings,
    # otherwise re-opening the same path can resurrect old pages.
    if reset and db_path.exists():
        for suffix in ("", "-shm", "-wal"):
            sibling = db_path.with_name(db_path.name + suffix)
            try:
                sibling.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.warning("init-db --reset: could not delete %s: %s", sibling, exc)
        print(_amber(f"Reset: deleted previous DB at {db_path}"))
    elif db_path.exists():
        # Friendly warning, non-blocking — matches the spec.
        print(_yellow(f"Existing database at {db_path} — re-using.") + _dim(" Use --reset to start fresh."))

    print(
        _u("Initialising data directory at ", "Initialising data directory at ")
        + f"{_bold(str(data_dir))}"
        + _u("…", "...")
    )
    _setup_env(data_dir, DEFAULT_HOST, DEFAULT_PORT)

    # Trigger the same SQLite auto-migration that main.py does on startup,
    # so `init-db` actually creates the tables and the first `serve` starts
    # instantly without table creation lag.
    import asyncio

    # Mirrors the list in main.py's startup hook — keep the two lists in
    # sync when adding a new module.
    _module_names = [
        "ai",
        "assemblies",
        "bim_hub",
        "boq",
        "catalog",
        "cde",
        "changeorders",
        "collaboration",
        "contacts",
        "correspondence",
        "costmodel",
        "costs",
        "documents",
        "enterprise_workflows",
        "erp_chat",
        "fieldreports",
        "finance",
        "full_evm",
        "i18n_foundation",
        "inspections",
        "integrations",
        "markups",
        "meetings",
        "ncr",
        "notifications",
        "procurement",
        "projects",
        "punchlist",
        "reporting",
        "requirements",
        "rfi",
        "rfq_bidding",
        "risk",
        "safety",
        "schedule",
        "submittals",
        "takeoff",
        "tasks",
        "teams",
        "tendering",
        "transmittals",
        "users",
        "validation",
    ]

    # Track import failures so we can report them loudly. Silently
    # swallowing these (as the pre-v1.3.14 code did) led to "no such
    # table" errors at runtime — the user saw "Ready." during init-db
    # and then the server 500'd on the first query to a missing model.
    failed_imports: list[tuple[str, str]] = []
    imported_ok = 0

    async def _create() -> None:
        nonlocal imported_ok
        import importlib

        from app.database import Base, engine

        for name in _module_names:
            try:
                importlib.import_module(f"app.modules.{name}.models")
                imported_ok += 1
            except ImportError as exc:
                failed_imports.append((name, f"ImportError: {exc}"))
                logger.warning("init-db: failed to import app.modules.%s.models: %s", name, exc)
            except Exception as exc:  # noqa: BLE001
                # Non-ImportError (e.g. syntax error, attribute error) is
                # still a real problem — record it.
                failed_imports.append((name, f"{type(exc).__name__}: {exc}"))
                logger.warning(
                    "init-db: %s while importing app.modules.%s.models: %s",
                    type(exc).__name__,
                    name,
                    exc,
                )

        try:
            from app.core.sqlite_migrator import sqlite_auto_migrate

            await sqlite_auto_migrate(engine, Base)
        except Exception as exc:  # noqa: BLE001
            logger.warning("init-db: sqlite_auto_migrate skipped: %s", exc)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        asyncio.run(_create())
    except Exception as exc:
        print(_red(f"Database initialisation failed: {exc}"))
        print(_dim(f"  {_u('\u2192', '->')} Run 'openconstructionerp doctor' for diagnostics."))
        sys.exit(1)

    total = len(_module_names)
    print()
    print(f"  {_dim('Modules:')}  imported {imported_ok}/{total} module models")

    if failed_imports:
        print()
        print(_red(_bold(f"  {len(failed_imports)} module(s) failed to import:")))
        for name, err in failed_imports:
            print(f"    - {_bold(name)}: {_dim(err)}")
        print()
        print(_red("Schema may be incomplete. Reinstall the package or check the error above."))
        print(_dim(f"  {_u('\u2192', '->')} pip install --upgrade --force-reinstall openconstructionerp"))
        print(_dim(f"  {_u('\u2192', '->')} Then run 'openconstructionerp doctor' to verify."))
        sys.exit(1)

    print()
    print(_green(_bold("Ready.")))
    print(f"  {_dim('Database:')} {data_dir / 'openestimate.db'}")
    print(f"  {_dim('Vectors:')}  {data_dir / 'vectors'}")
    print(f"  {_dim('Uploads:')}  {data_dir / 'uploads'}")
    print()
    print(f"Next: {_amber('openconstructionerp serve')}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run pre-flight checks and report OK / WARN / ERROR per item."""
    data_dir = Path(args.data_dir).expanduser().resolve()

    print()
    print(_bold(_u("OpenConstructionERP \u2014 doctor", "OpenConstructionERP - doctor")))
    print(_dim(f"Checking install at {data_dir}"))
    print()

    checks = run_preflight(args.host, args.port, data_dir, verbose=True)
    for c in checks:
        c.print()

    errors = [c for c in checks if c.status == "error"]
    warns = [c for c in checks if c.status == "warn"]

    print()
    if errors:
        print(_red(_bold(f"  {len(errors)} error(s)")) + _dim(f", {len(warns)} warning(s)"))
        print()
        print(_dim("Fix the errors above, then run 'openconstructionerp serve'."))
        print(_dim(f"Docs: {TROUBLESHOOTING_URL}"))
        sys.exit(1)
    elif warns:
        print(
            _yellow(_bold(f"  {len(warns)} warning(s)"))
            + _dim(_u(" \u2014 non-fatal, server will run", " - non-fatal, server will run"))
        )
        print()
        print(f"Run: {_amber('openconstructionerp serve')}")
    else:
        print(_green(_bold("  All checks passed.")))
        print()
        print(f"Run: {_amber('openconstructionerp serve')}")


def cmd_version(_args: argparse.Namespace) -> None:
    """Print version information."""
    try:
        from importlib.metadata import version as _v

        version = _v("openconstructionerp")
    except Exception:
        try:
            from app.config import Settings

            version = Settings.model_fields["app_version"].default
        except Exception:
            version = "unknown"

    print(f"OpenConstructionERP v{version}")
    print(f"Python {sys.version.split()[0]} ({sys.platform})")
    print(f"Site-packages: {Path(sys.executable).parent}")
    print(f"Docs: {DOCS_URL}")


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Pip-upgrade openconstructionerp inside *this* interpreter's environment.

    Issue #96: users who installed via the Windows installer get a launcher
    (``start.bat``) that points at a private venv under
    ``%LOCALAPPDATA%\\OpenConstructionERP\\venv``. Running ``pip install
    --upgrade openconstructionerp`` in any other shell upgrades the user's
    GLOBAL Python — the venv keeps its old wheel, and the launcher keeps
    reporting the old version even though pip claims success. This command
    avoids the trap by always invoking ``sys.executable -m pip`` so the
    upgrade lands in the same env that ``serve`` runs in.
    """
    import subprocess

    print()
    print(_bold(_u("OpenConstructionERP \u2014 upgrade", "OpenConstructionERP - upgrade")))

    target = "openconstructionerp"
    if args.version:
        target = f"openconstructionerp=={args.version}"

    print(_dim(f"Interpreter: {sys.executable}"))
    print(_dim(f"Installing:  {target}"))
    print()

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", target]
    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        print(_red(f"pip not found in this interpreter: {exc}"))
        sys.exit(1)

    if result.returncode != 0:
        print()
        print(_red(_bold(f"  Upgrade failed (exit {result.returncode})")))
        print(_dim("Try: python -m pip install --upgrade openconstructionerp"))
        sys.exit(result.returncode)

    new_version = _resolve_version()
    print()
    print(_green(_bold(f"  Upgraded to v{new_version}")))
    print(_dim("Restart your launcher (start.bat / openconstructionerp serve) to pick it up."))


def _resolve_version() -> str:
    """Best-effort version lookup shared by welcome/version commands."""
    try:
        from importlib.metadata import version as _v

        return _v("openconstructionerp")
    except Exception:
        try:
            from app.config import Settings

            return Settings.model_fields["app_version"].default
        except Exception:
            return "unknown"


def print_welcome(*, next_command_hint: bool = True) -> None:
    """Fast, zero-network welcome screen.

    Shown on the first bare ``openconstructionerp`` invocation and when
    the user runs ``openconstructionerp welcome`` explicitly. Tells them
    the single command that starts everything, the demo login, and where
    to ask questions when something goes wrong.

    ``next_command_hint`` distinguishes the two contexts. When True the
    user typed ``welcome`` and no server is starting, so we tell them the
    command that does. When False this is the first-run bare command and
    the server is about to auto-start, so we say so instead.
    """
    version = _resolve_version()
    bar = _bar()
    url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
    print()
    print(_amber(_BANNER_ART))
    print()
    print(f"  {_bold('OpenConstructionERP')} {_dim('v' + version)}")
    print(f"  {_dim('Open-source construction cost estimation platform')}")
    print()
    if next_command_hint:
        print(f"  {bar}  {_bold('To start, run one command')}")
        print(f"  {bar}     {_amber('openconstructionerp')}")
        print(f"  {bar}  {_dim('It sets up the database, loads the demo and opens your browser.')}")
    else:
        print(f"  {bar}  {_bold('Setting things up for you')}")
        print(f"  {bar}  {_dim('Creating the database and loading the demo. The server starts in a moment.')}")
    print(f"  {bar}")
    print(f"  {bar}  {_bold('Then log in')}")
    print(f"  {bar}     {_amber(url)}")
    print(f"  {bar}     demo@openconstructionerp.com  {_dim('/')}  DemoPass1234!")
    print()
    print(f"  {_dim('Advanced:')}  openconstructionerp serve {_dim('|')} init-db {_dim('|')} doctor {_dim('|')} --help")
    print()
    print(f"  {_bold('Help and community')}")
    print(f"    {_dim('Docs'.ljust(10))} {DOCS_URL}")
    print(f"    {_dim('GitHub'.ljust(10))} {GITHUB_URL}")
    print(f"    {_dim('Community'.ljust(10))} {COMMUNITY_URL} {_dim('(Telegram)')}")
    print()
    if next_command_hint:
        print(f"  {_dim('Tip: run')} {_amber('openconstructionerp')} {_dim('again any time to start the server.')}")
        print()


def cmd_welcome(_args: argparse.Namespace) -> None:
    """Print the welcome screen and exit — no server, no I/O."""
    print_welcome(next_command_hint=True)


def _prompt_open_browser(url: str, default_open: bool = True) -> bool:
    """Ask whether to open the browser on first-run.

    Returns True if the user presses ``o`` (or just Enter when the
    default is open), False if they decline. Safe against non-TTY
    invocations (CI, piped input) — returns ``default_open`` and moves
    on without blocking.

    The prompt is deliberately short so the user can hit Enter in under
    a second without reading the whole sentence.
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return default_open

    default_hint = "[O/n]" if default_open else "[o/N]"
    prompt = f"  {_bold('Open')} {_amber(url)} {_dim('in your browser now?')} {_dim(default_hint)} "
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer == "":
        return default_open
    return answer.startswith("o") or answer in ("y", "yes", "да", "д")


def cmd_seed(args: argparse.Namespace) -> None:
    """Load demo data into the database."""
    data_dir = Path(args.data_dir).expanduser().resolve()
    _setup_env(data_dir, DEFAULT_HOST, DEFAULT_PORT)

    import asyncio

    async def _run_seed() -> None:
        from app.config import get_settings

        settings = get_settings()
        if "sqlite" in settings.database_url:
            from app.database import Base, engine
            from app.modules.boq import models as _  # noqa: F401
            from app.modules.costs import models as _  # noqa: F401
            from app.modules.projects import models as _  # noqa: F401
            from app.modules.users import models as _  # noqa: F401

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        print("Database tables created.")

        if args.demo:
            print(_u("Loading demo project data…", "Loading demo project data..."))
            from app.core.demo_projects import install_demo_project
            from app.database import async_session_factory

            async with async_session_factory() as session:
                result = await install_demo_project(session, "office_tower_berlin")
                await session.commit()
                print(f"Demo project installed: {result.get('project_name', 'OK')}")

        print("Seed complete.")

    asyncio.run(_run_seed())


# ── Module management (install / list / uninstall) ─────────────────────────
# A module is a Python package under ``app/modules/`` that carries a
# ``manifest.py`` exposing a module-level ``manifest = ModuleManifest(...)``.
# The loader (``app.core.module_loader``) discovers modules by scanning that
# directory for ``manifest.py`` and registers each by ``manifest.name`` (e.g.
# ``oe_boq``). The on-disk directory name is ``manifest.name`` with the
# ``oe_`` prefix stripped (``oe_boq`` -> ``boq``), which is the convention
# ``_load_module`` uses to resolve the importable package path. These commands
# extract / remove modules into exactly that directory so the loader picks
# them up on the next server start.


def _modules_dir() -> Path:
    """Return the directory the module loader scans for modules.

    Imports the loader so we always agree with it on the location, instead of
    re-deriving the path here and risking drift.
    """
    from app.core.module_loader import MODULES_DIR

    return MODULES_DIR


def _module_dir_name(manifest_name: str) -> str:
    """Map a manifest name to its on-disk package directory name.

    Mirrors ``ModuleLoader._load_module`` (``dir_name = name.removeprefix('oe_')``).
    """
    return manifest_name.removeprefix("oe_")


def _read_manifest_name(source: str) -> str | None:
    """Extract ``manifest.name`` from a ``manifest.py`` source string.

    Parsed statically with ``ast`` rather than imported, so installing a module
    never executes untrusted code just to learn its name. Looks for a top-level
    assignment ``<target> = ModuleManifest(... name="...", ...)`` and returns the
    literal ``name`` keyword. Returns ``None`` if it cannot be found.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        callee = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if callee != "ModuleManifest":
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return None


def _is_unsafe_zip_member(info: object) -> str | None:
    """Return a human-readable reason if a zip member is unsafe, else None.

    Rejects:
      * absolute POSIX paths (``/etc/passwd``)
      * parent-directory traversal (any ``..`` path segment)
      * Windows drive letters / backslash separators (``C:\\evil``, ``a\\b``)
      * symlinks (encoded in the Unix mode bits of ``external_attr``)
    """
    import stat

    name = getattr(info, "filename", "")

    # Windows drive letter, e.g. "C:..." — also catches "C:\\..." once \\ -> /.
    if len(name) >= 2 and name[1] == ":":
        return f"drive-letter path: {name!r}"

    # Normalise backslashes so a Windows-authored archive can't smuggle
    # traversal past the POSIX checks below.
    if "\\" in name:
        return f"backslash separator in path: {name!r}"

    if name.startswith("/"):
        return f"absolute path: {name!r}"

    parts = name.split("/")
    if ".." in parts:
        return f"parent-directory traversal: {name!r}"

    # Symlink detection: the high 16 bits of external_attr hold the Unix mode.
    external_attr = getattr(info, "external_attr", 0)
    mode = external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        return f"symlink member: {name!r}"

    return None


def cmd_module_install(args: argparse.Namespace) -> None:
    """Install a module from a .zip archive into the modules directory."""
    import zipfile

    zip_path = Path(args.zip).expanduser().resolve()

    if not zip_path.exists():
        print(_red(f"Archive not found: {zip_path}"))
        sys.exit(1)

    if not zipfile.is_zipfile(zip_path):
        print(_red(f"Not a valid zip archive: {zip_path}"))
        sys.exit(1)

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if not infos:
            print(_red("Archive is empty."))
            sys.exit(1)

        # 1. Reject any unsafe member before touching the filesystem.
        for info in infos:
            reason = _is_unsafe_zip_member(info)
            if reason is not None:
                print(_red(f"Refusing to install — unsafe archive member ({reason})."))
                sys.exit(1)

        # 2. Require exactly one top-level package directory. Every member must
        #    live under it (a flat archive with files at the root is rejected).
        top_levels: set[str] = set()
        for info in infos:
            first = info.filename.split("/", 1)[0]
            if first:
                top_levels.add(first)
        if len(top_levels) != 1:
            print(
                _red(
                    "Archive must contain exactly one top-level package directory "
                    f"(found {len(top_levels)}: {', '.join(sorted(top_levels)) or 'none'})."
                )
            )
            sys.exit(1)
        top = next(iter(top_levels))

        # 3. The top-level entry must be a directory, not a single file.
        if not any(i.filename.rstrip("/") != top for i in infos):
            print(_red(f"Top-level entry {top!r} is a file, not a package directory."))
            sys.exit(1)

        # 4. Locate the manifest at the top level: ``<top>/manifest.py``.
        manifest_arcname = f"{top}/manifest.py"
        names = {i.filename for i in infos}
        if manifest_arcname not in names:
            print(
                _red(
                    f"No manifest found at {manifest_arcname!r}. "
                    "A module package must contain a top-level manifest.py."
                )
            )
            sys.exit(1)

        # 5. Read the module name from the manifest (static parse, no exec).
        try:
            manifest_src = zf.read(manifest_arcname).decode("utf-8")
        except (KeyError, UnicodeDecodeError) as exc:
            print(_red(f"Could not read {manifest_arcname}: {exc}"))
            sys.exit(1)

        module_name = _read_manifest_name(manifest_src)
        if not module_name:
            print(
                _red(
                    "Could not determine the module name from manifest.py "
                    "(expected ModuleManifest(name=\"...\", ...))."
                )
            )
            sys.exit(1)

        # 6. Resolve the canonical on-disk directory name and target path.
        dir_name = _module_dir_name(module_name)
        modules_dir = _modules_dir()
        target = modules_dir / dir_name

        if target.exists():
            if not args.force:
                print(
                    _red(f"Module '{module_name}' already installed at {target}.")
                    + _dim(" Use --force to overwrite.")
                )
                sys.exit(1)
            import shutil

            shutil.rmtree(target)

        # 7. Safe extraction into a temp staging dir, then atomically move the
        #    package into place under its canonical directory name. Staging
        #    first means a mid-extract failure never leaves a half-written
        #    module in the loader's scan path. Re-validate each member name at
        #    extraction time (defence in depth against a member that slipped
        #    through, e.g. via a crafted ZipInfo).
        import shutil
        import tempfile

        modules_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="oe_module_install_"))
        try:
            staged_root = staging.resolve()
            for info in infos:
                # Skip directory entries — created implicitly by file writes.
                if info.filename.endswith("/"):
                    continue
                dest = (staging / info.filename).resolve()
                if not str(dest).startswith(str(staged_root) + os.sep) and dest != staged_root:
                    print(_red(f"Refusing to install — member escapes staging dir: {info.filename!r}."))
                    sys.exit(1)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

            staged_pkg = staging / top
            if not staged_pkg.is_dir():
                print(_red("Extraction did not produce the expected package directory."))
                sys.exit(1)

            shutil.move(str(staged_pkg), str(target))
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    print(_green(_bold(f"Installed module: {module_name}")) + _dim(f"  ({target})"))
    print("Restart the server to load the module.")


def _discover_manifests() -> dict[str, object]:
    """Discover all module manifests via the real loader, return name -> manifest.

    Uses a fresh ``ModuleLoader`` (not the global singleton) so a CLI ``list``
    never mutates shared process state.
    """
    from app.core.module_loader import ModuleLoader

    loader = ModuleLoader()
    loader.discover()
    return dict(loader._manifests)


def cmd_module_list(_args: argparse.Namespace) -> None:
    """List discovered modules with version and enabled/core status."""
    from app.core.module_state import load_module_states

    manifests = _discover_manifests()
    if not manifests:
        print(_dim("No modules found."))
        return

    states = load_module_states()

    rows: list[tuple[str, str, str, str]] = []
    for name in sorted(manifests):
        manifest = manifests[name]
        version = getattr(manifest, "version", "?")
        category = getattr(manifest, "category", "")
        is_core = category == "core"
        # A non-core module is disabled only if persisted state says so.
        state = states.get(name)
        enabled = True if state is None else state.enabled
        if is_core:
            status = "core"
        else:
            status = "enabled" if enabled else "disabled"
        rows.append((name, version, category, status))

    name_w = max((len(r[0]) for r in rows), default=4)
    ver_w = max((len(r[1]) for r in rows), default=7)
    cat_w = max((len(r[2]) for r in rows), default=8)

    header = f"  {'NAME'.ljust(name_w)}  {'VERSION'.ljust(ver_w)}  {'CATEGORY'.ljust(cat_w)}  STATUS"
    print(_bold(header))
    for name, version, category, status in rows:
        if status == "core":
            badge = _dim("core")
        elif status == "enabled":
            badge = _green("enabled")
        else:
            badge = _yellow("disabled")
        print(f"  {name.ljust(name_w)}  {version.ljust(ver_w)}  {category.ljust(cat_w)}  {badge}")

    print()
    print(_dim(f"{len(rows)} module(s) in {_modules_dir()}"))


def cmd_module_uninstall(args: argparse.Namespace) -> None:
    """Remove an installed module's package directory."""
    import shutil

    requested = args.name
    manifests = _discover_manifests()

    # Accept either the manifest name (oe_foo) or the directory name (foo).
    manifest = manifests.get(requested)
    if manifest is None:
        manifest = manifests.get(f"oe_{requested}")

    if manifest is None:
        print(_red(f"Module '{requested}' is not installed."))
        print(_dim("Run 'openconstructionerp module list' to see installed modules."))
        sys.exit(1)

    manifest_name = getattr(manifest, "name", requested)
    is_core = getattr(manifest, "category", "") == "core"
    auto_install = bool(getattr(manifest, "auto_install", False))

    if (is_core or auto_install) and not args.force:
        kind = "core" if is_core else "auto-install"
        print(
            _red(f"Refusing to uninstall '{manifest_name}' — it is a {kind} module.")
            + _dim(" Use --force to remove it anyway.")
        )
        sys.exit(1)

    dir_name = _module_dir_name(manifest_name)
    target = _modules_dir() / dir_name
    if not target.exists():
        print(_red(f"Module directory not found: {target}"))
        sys.exit(1)

    shutil.rmtree(target)
    print(_green(_bold(f"Uninstalled module: {manifest_name}")) + _dim(f"  ({target})"))
    print("Restart the server to apply the change.")


def cmd_module(args: argparse.Namespace) -> None:
    """Dispatch ``module`` sub-actions; print help when none is given."""
    action = getattr(args, "module_action", None)
    if action == "install":
        cmd_module_install(args)
    elif action == "list":
        cmd_module_list(args)
    elif action == "uninstall":
        cmd_module_uninstall(args)
    else:
        # No sub-action: print the module group's help.
        args._module_parser.print_help()


# ── Arg parser ────────────────────────────────────────────────────────────
def _add_common_server_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})")
    p.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Data directory (default: {DEFAULT_DATA_DIR})",
    )
    p.add_argument(
        "--embedded-pg",
        action="store_true",
        help="Run an in-process PostgreSQL (no Docker); data in <data-dir>/pgdata (this is the default)",
    )
    p.add_argument(
        "--sqlite",
        action="store_true",
        help="Use the legacy single-file SQLite database instead of embedded PostgreSQL",
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="openconstructionerp",
        description=(
            "OpenConstructionERP, open-source construction cost estimation platform.\n\n"
            "Quick start, one command does everything:\n"
            "    openconstructionerp\n\n"
            "It creates the local database, loads the demo data, starts the server\n"
            "and opens http://127.0.0.1:8080 (demo@openconstructionerp.com / DemoPass1234!)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_p = subparsers.add_parser("serve", help="Start the OpenConstructionERP server")
    _add_common_server_args(serve_p)
    serve_p.add_argument("--open", action="store_true", help="Open browser after startup")
    serve_p.add_argument("--quiet", action="store_true", help="Suppress banner and info logs")

    # init-db (canonical) + init (alias for backward compat)
    init_db_p = subparsers.add_parser(
        "init-db",
        help="Create the local SQLite database and data directories",
    )
    init_db_p.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Data directory (default: {DEFAULT_DATA_DIR})",
    )
    init_db_p.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing openestimate.db (and -shm/-wal) before init",
    )
    # Legacy alias — same args, same handler.
    init_p = subparsers.add_parser("init", help="Alias for init-db")
    init_p.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Data directory (default: {DEFAULT_DATA_DIR})",
    )
    init_p.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing openestimate.db (and -shm/-wal) before init",
    )

    # doctor
    doctor_p = subparsers.add_parser("doctor", help="Run installation health checks")
    _add_common_server_args(doctor_p)

    # version
    subparsers.add_parser("version", help="Show version information")

    # upgrade — pip-upgrade in *this* interpreter's env (Issue #96)
    upgrade_p = subparsers.add_parser(
        "upgrade",
        help="Upgrade openconstructionerp in the same env this command runs in",
    )
    upgrade_p.add_argument(
        "--version",
        default=None,
        help="Pin to a specific version (e.g. --version 2.6.10). Defaults to latest.",
    )

    # welcome (zero-network greeting + quick-start + support links)
    subparsers.add_parser(
        "welcome",
        help="Print a welcome screen with quick-start commands and support links",
    )
    subparsers.add_parser(
        "hello",
        help="Alias for 'welcome'",
    )

    # seed
    seed_p = subparsers.add_parser("seed", help="Load seed/demo data")
    seed_p.add_argument("--demo", action="store_true", help="Install demo project with sample data")
    seed_p.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Data directory (default: {DEFAULT_DATA_DIR})",
    )

    # module — install / list / uninstall business modules
    module_p = subparsers.add_parser(
        "module",
        help="Install, list, or uninstall modules",
        description=(
            "Manage OpenConstructionERP modules.\n\n"
            "    openconstructionerp module install <archive.zip> [--force]\n"
            "    openconstructionerp module list\n"
            "    openconstructionerp module uninstall <name> [--force]\n\n"
            "A module is a Python package with a manifest.py. Install extracts it\n"
            "into the modules directory; restart the server to load it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    module_sub = module_p.add_subparsers(dest="module_action")

    module_install_p = module_sub.add_parser("install", help="Install a module from a .zip archive")
    module_install_p.add_argument("zip", help="Path to the module .zip archive")
    module_install_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing module of the same name",
    )

    module_sub.add_parser("list", help="List discovered modules (name, version, status)")

    module_uninstall_p = module_sub.add_parser("uninstall", help="Remove an installed module")
    module_uninstall_p.add_argument("name", help="Module name (oe_foo) or directory name (foo)")
    module_uninstall_p.add_argument(
        "--force",
        action="store_true",
        help="Remove even core / auto-install modules",
    )

    args = parser.parse_args()

    # Make the module group's parser reachable from cmd_module so it can print
    # help when invoked with no sub-action (``openconstructionerp module``).
    if args.command == "module":
        args._module_parser = module_p

    # Embedded PostgreSQL is the default (see embedded_pg.is_requested). The
    # flags are explicit overrides mapped to the same env vars _setup_env reads
    # before any app module (and therefore the engine) is imported:
    #   --sqlite      → OE_USE_SQLITE=1     (escape hatch to legacy SQLite)
    #   --embedded-pg → OE_USE_EMBEDDED_PG=1 (explicit; already the default)
    if getattr(args, "sqlite", False):
        os.environ["OE_USE_SQLITE"] = "1"
    if getattr(args, "embedded_pg", False):
        os.environ["OE_USE_EMBEDDED_PG"] = "1"

    if args.command == "serve":
        cmd_serve(args)
    elif args.command in ("init-db", "init"):
        cmd_init_db(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "version":
        cmd_version(args)
    elif args.command == "upgrade":
        cmd_upgrade(args)
    elif args.command == "seed":
        cmd_seed(args)
    elif args.command == "module":
        cmd_module(args)
    elif args.command in ("welcome", "hello"):
        cmd_welcome(args)
    elif args.command is None:
        # Default behaviour for bare ``openconstructionerp``:
        # * First run (no data dir yet) - show the welcome screen and an
        #   interactive "open in browser?" prompt so the user sees the URL,
        #   demo login and community links BEFORE uvicorn eats the
        #   terminal for the startup wait.
        # * Subsequent runs - jump straight to serve (they already know).
        data_dir = Path(DEFAULT_DATA_DIR)
        first_run = not data_dir.exists() or not (data_dir / "openestimate.db").exists()
        args.host = DEFAULT_HOST
        args.port = DEFAULT_PORT
        args.data_dir = str(DEFAULT_DATA_DIR)
        args.quiet = False

        if first_run:
            print_welcome(next_command_hint=False)
            url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
            # Press 'o' (or Enter) to let the server open the browser
            # after it has bound the socket; any other answer keeps the
            # terminal focused (useful for SSH sessions).
            args.open = _prompt_open_browser(url, default_open=True)
            print()
            print(
                _dim(
                    _u(
                        "  Starting the server now \u2014 press Ctrl+C to stop.",
                        "  Starting the server now - press Ctrl+C to stop.",
                    ),
                ),
            )
            print()
        else:
            args.open = True
        cmd_serve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
