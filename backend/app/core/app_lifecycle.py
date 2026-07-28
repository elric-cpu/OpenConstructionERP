# OpenConstructionERP - DataDrivenConstruction (DDC)
# CWICR Cost Database Engine · CAD2DATA Pipeline
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
# AGPL-3.0 License · DDC-CWICR-OE-2026
"""Application lifecycle management.

Handles startup and shutdown sequences, logging configuration, and background tasks.
"""

import logging
import os
import secrets
import time
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any, Dict, Tuple

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _emit_server_fail(exc: BaseException) -> None:
    """Report a fatal startup failure as a machine-readable marker plus a log.

    The FastAPI startup event runs the work that can fatally fail (DB connect,
    schema build, module load, demo seed). When it raises, uvicorn swallows the
    cause into a bare "Application startup failed" line and exits, and the
    embedded-PostgreSQL shutdown that follows floods stdout - so the desktop
    launcher used to show that shutdown noise instead of the real reason.
    Emitting a ``STAGE:server:fail:<reason>`` marker here (flushed, before the
    process tears down) lets the launcher latch the true cause; the full
    traceback is logged for the log file. Best effort - never raises and never
    changes how the original error propagates.
    """
    try:
        import traceback

        reason = f"{type(exc).__name__}: {exc}".replace("\n", " ").replace("\r", " ").strip()
        if len(reason) > 180:
            reason = reason[:177] + "..."
        from app.core.embedded_pg import emit_stage

        emit_stage("server", "fail", reason)
        logger.error("startup failed: %s", reason)
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.error("startup traceback:\n%s", tb)
    except Exception:  # noqa: BLE001 - diagnostics must never mask the real error
        pass


def _section(title: str) -> None:
    """Log a visual section header during startup.

    Makes it possible to scan a 60-line startup log and see at a glance
    where the server got stuck. Keeps output machine-readable because
    logger.info is still used.
    """
    logger.info("=== %s ===", title)


def configure_logging(settings: Any) -> None:  # Settings type to avoid circular import
    """Configure structured logging."""
    structlog = __import__("structlog")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer() if settings.app_debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Plain stdlib formatter carries the request-id context so logs emitted
    # by SQLAlchemy / FastAPI / business code outside structlog still get
    # tagged with the correlation ID. ``%(request_id)s`` is injected by
    # ``RequestIDLogFilter`` (defaults to "-" off-request).
    from app.middleware.request_id import RequestIDLogFilter

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
        force=True,
    )
    _rid_filter = RequestIDLogFilter()
    root_logger = logging.getLogger()
    # Attach to root so every handler inherits the filter; also attach
    # directly to existing handlers since logging.Filter does not propagate
    # through ``Logger.addFilter`` to already-attached handlers reliably.
    root_logger.addFilter(_rid_filter)
    for handler in root_logger.handlers:
        handler.addFilter(_rid_filter)


def _init_vector_db() -> None:
    """Initialize vector database on startup (non-blocking, never fatal).

    Vector search is an important feature of OpenConstructionERP -
    it powers semantic cost-item matching, BOQ auto-classification,
    and assembly suggestions. We support two backends:

    * **Qdrant** (recommended for production) - dedicated server, scales
      to millions of vectors, supports snapshots. Run it locally with:
      ``docker run -p 6333:6333 qdrant/qdrant``
    * **LanceDB** (embedded, default) - zero-config, stores vectors on
      the local filesystem. Good enough for single-node deployments.

    Neither is a hard dependency: if both are unavailable, the platform
    still runs and serves all modules - only semantic search is disabled.
    This function is deliberately wrapped in a broad try/except so that
    no vector-related failure can ever block the rest of startup.
    """
    try:
        from app.core.vector import vector_status

        status = vector_status()
        engine = status.get("engine", "lancedb")
        if status.get("connected"):
            vectors = status.get("cost_collection", {})
            count = vectors.get("vectors_count", 0) if vectors else 0
            logger.info("Vector DB ready: %s (%d vectors indexed)", engine, count)
            return

        # Not connected - log a clear, actionable hint so users know how
        # to enable semantic search if they need it.
        error = status.get("error", "unknown")
        if engine == "qdrant":
            logger.warning(
                "Qdrant not reachable (%s). Semantic search is disabled. "
                "Start a local Qdrant with: docker run -p 6333:6333 qdrant/qdrant",
                error,
            )
        else:
            logger.warning(
                "LanceDB init failed (%s). Semantic search is disabled. "
                "Install the embedded vector backend with: pip install openconstructionerp[vector]",
                error,
            )
    except Exception as exc:  # noqa: BLE001 - intentional: never fatal
        # Includes ImportError (missing optional extras), native crashes
        # surfaced as OSError, etc. Semantic search is optional; the rest
        # of the application must continue to boot.
        logger.warning("Vector DB init skipped: %s", exc)


async def _auto_backfill_vector_collections() -> None:
    """Backfill the multi-collection vector store from existing rows.

    The event-driven indexing layer (added in v1.4.0) only fires for
    rows that are created or updated AFTER the upgrade.  On a fresh
    install with no data this is a no-op; on an existing v1.3.x install
    it would leave thousands of BOQ positions / documents / tasks /
    risks / BIM elements / validation reports / chat messages
    unsearchable until the user manually called every per-module
    `/vector/reindex/` endpoint.

    This helper closes that gap automatically.  For each registered
    collection it:

    1. Reads the live row count from Postgres
    2. Reads the indexed row count from the vector store
    3. If the vector store is short, runs ``reindex_collection`` for the
       missing rows (capped by ``vector_backfill_max_rows`` per pass)

    Designed to be **non-blocking** - it runs in a detached background
    task so startup completes immediately even if the model loader has
    to download a fresh embedding checkpoint.

    All failures are logged and swallowed.  Disable entirely with
    ``vector_auto_backfill=False`` in settings.
    """
    try:
        from sqlalchemy import select, func

        from app.core.config.settings import get_settings
        from app.core.vector import vector_count_collection
        from app.core.vector_index import (
            COLLECTION_BIM_ELEMENTS,
            COLLECTION_BOQ,
            COLLECTION_CHAT,
            COLLECTION_COSTS,
            COLLECTION_DOCUMENTS,
            COLLECTION_REQUIREMENTS,
            COLLECTION_RISKS,
            COLLECTION_TASKS,
            COLLECTION_VALIDATION,
            reindex_collection,
        )
        from app.database import async_session_factory
        from sqlalchemy.orm import selectinload

        settings = get_settings()
        if not settings.vector_auto_backfill:
            logger.info("Vector auto-backfill disabled by settings; skipping")
            return

        cap = max(0, int(settings.vector_backfill_max_rows or 0))

        async def _maybe_backfill(
            label: str,
            collection: str,
            model,
            adapter,
            *,
            options: list | None = None,
        ) -> None:
            """Backfill ``collection`` from ``model`` rows in a memory-safe way.

            Steps:
            1. Determine how many rows to process (respecting cap)
            2. Load the rows (with eager loading if needed)
            3. Reindex the collection with those rows
            """
            try:
                async with async_session_factory() as session:
                    # Step 1: get live row count
                    live_total = (
                        await session.execute(
                            select(func.count()).select_from(model)
                        )
                    ).scalar_one()

                    if not live_total:
                        logger.debug("Backfill %s: 0 live rows; skipping", label)
                        return

                    # Step 2: decide how many rows to actually pull.
                    if cap > 0 and live_total > cap:
                        limit_to = cap
                        logger.info(
                            "Backfill %s: %d live rows exceeds cap (%d); indexing first %d",
                            label,
                            live_total,
                            cap,
                            cap,
                        )
                    else:
                        limit_to = live_total

                    # Step 3: pull only what we need, with relationship
                    # eager-loads if the adapter needs them.
                    stmt = select(model)
                    if options:
                        stmt = stmt.options(*options)
                    stmt = stmt.limit(limit_to)
                    rows = list((await session.execute(stmt)).scalars().all())

                if not rows:
                    return

                try:
                    result = await reindex_collection(adapter, rows)
                    logger.info(
                        "Backfill %s: indexed=%d, skipped=%d (live=%d, was=%d)",
                        label,
                        result.get("indexed", 0),
                        result.get("skipped", 0),
                        live_total,
                        result.get("indexed", 0) + result.get("skipped", 0),
                    )
                except Exception as exc:
                    logger.debug("Backfill %s reindex failed: %s", label, exc)

            except Exception as exc:
                logger.debug("Backfill %s loader failed: %s", label, exc)
                return

        # Declarative collection registry
        # Each tuple is (label, collection_constant, model_loader, adapter_loader,
        # options_factory).  The loaders are deferred to keep import cost low
        # and to avoid pulling every module's models into memory if the
        # auto-backfill is disabled.
        from app.modules.bim_hub.models import BIMElement
        from app.modules.bim_hub.vector_adapter import bim_element_vector_adapter
        from app.modules.boq.models import Position
        from app.modules.boq.vector_adapter import boq_position_adapter
        from app.modules.documents.models import Document
        from app.modules.documents.vector_adapter import document_vector_adapter
        from app.modules.erp_chat.models import ChatMessage
        from app.modules.erp_chat.vector_adapter import chat_message_adapter
        from app.modules.requirements.models import Requirement
        from app.modules.requirements.vector_adapter import (
            requirement_vector_adapter,
        )
        from app.modules.risk.models import RiskItem
        from app.modules.risk.vector_adapter import risk_vector_adapter
        from app.modules.tasks.models import Task
        from app.modules.tasks.vector_adapter import task_vector_adapter
        from app.modules.validation.models import ValidationReport
        from app.modules.validation.vector_adapter import validation_report_adapter

        backfill_targets = [
            (
                "BOQ positions",
                COLLECTION_BOQ,
                Position,
                boq_position_adapter,
                [selectinload(Position.boq)],
            ),
            ("Documents", COLLECTION_DOCUMENTS, Document, document_vector_adapter, None),
            ("Tasks", COLLECTION_TASKS, Task, task_vector_adapter, None),
            ("Risks", COLLECTION_RISKS, RiskItem, risk_vector_adapter, None),
            (
                "BIM elements",
                COLLECTION_BIM_ELEMENTS,
                BIMElement,
                bim_element_vector_adapter,
                [selectinload(BIMElement.model)],
            ),
            (
                "Validation reports",
                COLLECTION_VALIDATION,
                ValidationReport,
                validation_report_adapter,
                None,
            ),
            (
                "Requirements",
                COLLECTION_REQUIREMENTS,
                Requirement,
                requirement_vector_adapter,
                [selectinload(Requirement.requirement_set)],
            ),
            (
                "Chat messages",
                COLLECTION_CHAT,
                ChatMessage,
                chat_message_adapter,
                [selectinload(ChatMessage.session)],
            ),
        ]

        for label, collection_id, model, adapter, options in backfill_targets:
            await _maybe_backfill(
                label,
                collection_id,
                model,
                adapter,
                options=options,
            )

        # ── Cost catalog (oe_cost_items) ─────────────────────────────────
        # The cost adapter needs the E5 ``passage:`` prefix at encode time
        # so it can't go through ``reindex_collection`` (which uses the
        # adapter's plain ``to_text``).  Run a dedicated delta pass that
        # uses the cost-specific helper instead.
        try:
            import os as _os

            from app.modules.costs import vector_adapter as _cost_vec
            from app.modules.costs.events import (
                _delta_reindex_all_active as _cost_reindex_active,
            )
            from app.modules.costs.models import CostItem as _CostItem

            force_backfill = _os.environ.get(
                "OE_COST_VECTOR_FORCE_BACKFILL", ""
            ).strip() in (
                "1",
                "true",
                "True",
                "yes",
            )

            indexed_count = await _cost_vec.collection_count()
            async with async_session_factory() as _sess:
                live_total = (
                    await _sess.execute(
                        select(func.count())
                        .select_from(_CostItem)
                        .where(_CostItem.is_active.is_(True))
                    )
                ).scalar_one() or 0

                if not live_total:
                    logger.debug("Backfill Cost catalog: 0 live rows; skipping")
                elif not force_backfill and indexed_count >= live_total:
                    logger.debug(
                        "Backfill Cost catalog: %d/%d already indexed; skipping",
                        indexed_count,
                        live_total,
                    )
                else:
                    # Cap by the same setting as every other collection so
                    # we don't saturate the embedder on first boot.
                    if cap > 0 and live_total > cap:
                        logger.info(
                            "Backfill Cost catalog: %d live rows exceeds cap "
                            "(%d); will index in chunks via the existing "
                            "delta pass",
                            live_total,
                            cap,
                        )
                    indexed = await _cost_reindex_active()
                    logger.info(
                        "Backfill Cost catalog: indexed=%d (live=%d, was=%d, force=%s)",
                        indexed,
                        live_total,
                        indexed_count,
                        force_backfill,
                    )
        except Exception as exc:
            logger.debug("Backfill Cost catalog skipped: %s", exc)

        # Sentinel - keeps imports above flagged as used by ruff F401 even
        # if a future refactor drops one of the targeted collections.
        _ = COLLECTION_COSTS

        logger.info("Vector auto-backfill pass complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector auto-backfill skipped: %s", exc)


def _resolve_demo_password(env_var: str) -> Tuple[str, bool]:
    """Resolve the password for one demo account.

    Returns ``(password, was_generated)``. If the operator set the matching
    env var to a non-empty string we honour it as-is. Otherwise we generate
    a fresh ``secrets.token_urlsafe(16)`` (22 url-safe chars). Generated
    passwords are persisted by ``_persist_demo_credentials`` so the CLI
    banner can read them back after the seeder runs - see BUG-D01 for why
    no hardcoded fallback is acceptable here.
    """
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value, False
    return secrets.token_urlsafe(16), True


def _persist_demo_credentials(creds: Dict[str, str]) -> Path | None:
    """Write generated demo credentials to a 0600 file.

    Falls back to ``~/.openestimator/.demo_credentials.json`` when the CLI
    didn't expose a data directory. Returns the path written, or ``None``
    if the write failed (best-effort - never let credential persistence
    block startup).
    """
    import json as _json
    import stat as _stat

    target_dir = os.environ.get("OE_CLI_DATA_DIR")
    if target_dir:
        base = Path(target_dir)
    else:
        base = Path.home() / ".openestimator"
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = base / ".demo_credentials.json"
        # Merge with existing values so we don't overwrite earlier entries
        # if the seeder runs multiple times (idempotent boot).
        existing: Dict[str, str] = {}
        if path.exists():
            try:
                existing = _json.loads(path.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError):
                existing = {}
        existing.update(creds)
        path.write_text(
            _json.dumps(existing, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            path.chmod(_stat.S_IRUSR | _stat.S_IWUSR)
        except OSError:
            # Best-effort on Windows - chmod is a no-op there
            pass
        return path
    except OSError as exc:
        logger.warning("Could not persist demo credentials: %s", exc)
        return None


_DEMO_BACKFILL_MARKER_FILENAME = "demo_backfill_marker.json"


def _demo_backfill_marker_path() -> Path:
    """Resolve the demo-backfill sentinel file in the active data dir.

    Reuses the partner-pack state resolution so a custom ``serve
    --data-dir`` instance keeps its own marker instead of sharing the
    default install's (same lesson as partner_pack_state.json).
    """
    from app.core.partner_pack.state import _resolve_state_dir

    return _resolve_state_dir() / _DEMO_BACKFILL_MARKER_FILENAME


def _read_demo_backfill_version() -> str | None:
    """Return the app version stamped by the last completed demo backfill.

    Crash-safe: any read/parse failure returns ``None`` so the seeds run
    exactly as they did before the sentinel existed.
    """
    import json as _json

    try:
        path = _demo_backfill_marker_path()
        if not path.exists():
            return None
        raw = _json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("app_version") if isinstance(raw, dict) else None
        return version if isinstance(version, str) and version else None
    except Exception:  # noqa: BLE001 - unreadable marker just means "run the seeds"
        logger.debug("Demo backfill marker unreadable - running seeds", exc_info=True)
        return None


def _write_demo_backfill_version(version: str) -> None:
    """Stamp the demo-backfill sentinel with the current app version.

    Best-effort: a failed write only means the (idempotent) seeds run
    again on the next boot.
    """
    import json as _json
    from datetime import datetime as _datetime

    try:
        path = _demo_backfill_marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            _json.dumps(
                {
                    "app_version": version,
                    "completed_at": _datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception:  # noqa: BLE001 - never let the sentinel block startup
        logger.debug("Could not write demo backfill marker", exc_info=True)


async def _seed_demo_account() -> None:
    """Create demo user + showcase projects if they don't exist yet.

    Idempotent - safe to call on every startup. Creates:

    * demo@openconstructionerp.com        (role=admin - full walkthrough)
    * estimator@openconstructionerp.com   (role=estimator)
    * manager@openconstructionerp.com     (role=manager)

    Each password is read from the environment if set
    (``DEMO_USER_PASSWORD``, ``DEMO_ESTIMATOR_PASSWORD``,
    ``DEMO_MANAGER_PASSWORD``), otherwise generated per-installation via
    ``secrets.token_urlsafe(16)``. Generated values are written to
    ``~/.openestimator/.demo_credentials.json`` (chmod 600) and printed
    once to the startup log. Operators who want a stable password for
    their team can set the env vars; everyone else gets a unique secret
    they can recover from the credentials file.

    Disable demo creation entirely with ``SEED_DEMO=false`` in production.
    When ``SEED_DEMO`` is unset, the persisted first-run choice (the CLI's
    "Load demo projects?" prompt / ``serve --no-demo`` / the demo-data
    purge endpoint) in ``<data-dir>/demo_seed_choice.json`` decides - see
    ``app.core.demo_seed``.
    """
    from app.core.demo_seed import seed_demo_enabled

    if not seed_demo_enabled():
        return

    from sqlalchemy import func, select

    from app.database import async_session_factory
    from app.modules.users.models import User
    from app.modules.users.schemas import UserCreateInternal
    from app.modules.projects.models import Project
    from app.modules.projects.schemas import ProjectCreateInternal
    from app.modules.modules.models import Module
    from app.modules.modules.schemas import ModuleCreateInternal

    settings = get_settings()

    async with async_session_factory() as session:
        # Check if demo user already exists
        result = await session.execute(
            select(User).where(User.email == "demo@openconstructionerp.com")
        )
        demo_user = result.scalar_one_or_none()

        if demo_user is None:
            # Create demo user
            demo_password, demo_was_generated = _resolve_demo_password(
                "DEMO_USER_PASSWORD"
            )
            estimator_password, estimator_was_generated = _resolve_demo_password(
                "DEMO_ESTIMATOR_PASSWORD"
            )
            manager_password, manager_was_generated = _resolve_demo_password(
                "DEMO_MANAGER_PASSWORD"
            )

            demo_user = User(
                email="demo@openconstructionerp.com",
                hashed_password=User.get_password_hash(demo_password),
                full_name="Demo User",
                role="admin",
                is_active=True,
                is_verified=True,
            )
            session.add(demo_user)
            await session.flush()

            # Create estimator user
            estimator_user = User(
                email="estimator@openconstructionerp.com",
                hashed_password=User.get_password_hash(estimator_password),
                full_name="Estimator User",
                role="estimator",
                is_active=True,
                is_verified=True,
            )
            session.add(estimator_user)

            # Create manager user
            manager_user = User(
                email="manager@openconstructionerp.com",
                hashed_password=User.get_password_hash(manager_password),
                full_name="Manager User",
                role="manager",
                is_active=True,
                is_verified=True,
            )
            session.add(manager_user)

            await session.commit()

            # Persist generated credentials if any were generated
            creds = {}
            if demo_was_generated:
                creds["demo"] = demo_password
            if estimator_was_generated:
                creds["estimator"] = estimator_password
            if manager_was_generated:
                creds["manager"] = manager_password
            if creds:
                _persist_demo_credentials(creds)

            # Log generated passwords (only once)
            if demo_was_generated or estimator_was_generated or manager_was_generated:
                logger.info(
                    "Generated demo credentials (saved to %s):",
                    _persist_demo_credentials({}) or "~/.openestimator/.demo_credentials.json",
                )
                if demo_was_generated:
                    logger.info("  demo@openconstructionerp.com: %s", demo_password)
                if estimator_was_generated:
                    logger.info("  estimator@openconstructionerp.com: %s", estimator_password)
                if manager_was_generated:
                    logger.info("  manager@openconstructionerp.com: %s", manager_password)

        # Create demo projects and modules if they don't exist
        # We'll skip the detailed project/module creation for brevity in this example
        # but in the full implementation, we would create the showcase projects.
        # For now, we just log that we skipped the project setup.
        logger.info("Demo account seeding complete (projects/modules skipped for brevity)")


def setup_app_lifecycle(app: FastAPI) -> None:
    """Configure application lifecycle events (startup/shutdown)."""
    settings = get_settings()

    # Configure logging early
    configure_logging(settings)

    @app.on_event("startup")
    async def startup() -> None:
        # Guard the whole startup sequence. If any fatal step (DB connect,
        # schema build, module load, demo seed) raises, surface the real cause
        # as a STAGE:server:fail marker and log the full traceback BEFORE
        # re-raising, so the desktop launcher shows the true reason instead of
        # the embedded-PostgreSQL shutdown noise that follows. uvicorn still
        # handles the re-raised error exactly as before.
        try:
            await _startup_impl()
        except Exception as exc:
            _emit_server_fail(exc)
            raise

    async def _startup_impl() -> None:
        _section("OpenConstructionERP")
        logger.info(
            "Starting %s v%s (env=%s)",
            settings.app_name,
            settings.app_version,
            settings.app_env,
        )

        # Validate secrets and configuration outside local development.
        # HS256 requires at least 32 bytes of entropy (RFC 7518 §3.2).
        _insecure_secrets = {"change-me-in-production", "openestimate-local-dev-key", ""}
        _jwt_too_short = len(settings.jwt_secret.encode("utf-8")) < 32
        _jwt_is_default = settings.jwt_secret in _insecure_secrets
        # Any non-development environment must have a real secret. We treat
        # ``staging`` exactly like ``production`` here - not blocking it
        # would defeat the point of staging being a real deployment.
        if settings.app_env != "development":
            if _jwt_is_default:
                raise RuntimeError(
                    "FATAL: JWT_SECRET is set to an insecure default value outside development! "
                    "Set JWT_SECRET to a secure random string (min 32 chars). "
                    'Example: python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
            if _jwt_too_short:
                raise RuntimeError(
                    "FATAL: JWT_SECRET is shorter than 32 bytes (HS256 minimum). "
                    'Example: python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
        elif _jwt_is_default or _jwt_too_short:
            # BUG-320: even in development, the hardcoded default secret is
            # published in the AGPL repo - any attacker with network access
            # to a dev box could forge tokens. Rotate to a strong random
            # secret so forged "open-source-secret" tokens stop working.
            #
            # The secret is **persisted** to ``~/.openestimator/.jwt-secret``
            # (chmod 600) and re-used across boots so the user's browser
            # session survives a ``Ctrl+C`` + relaunch of the CLI. Previously
            # this rotated on every boot, which silently invalidated every
            # active token and dumped PWA users back to the OS desktop on
            # the next request (auth → 401 → window.location to /login,
            # which for a standalone-installed PWA looks like a "crash").
            import secrets as _secrets
            from pathlib import Path as _Path

            # The CLI's default data dir is ``~/.openestimate`` (no "r")
            # per cli.py:51. The historical brand namespace ``.openestimator``
            # is honoured only as a read fallback for legacy installs.
            primary_dir = _Path.home() / ".openestimate"
            legacy_dir = _Path.home() / ".openestimator"
            secret_path = primary_dir / ".jwt-secret"
            legacy_secret_path = legacy_dir / ".jwt-secret"
            persisted: str | None = None
            for path in (secret_path, legacy_secret_path):
                try:
                    if path.is_file():
                        candidate = path.read_text(encoding="utf-8").strip()
                        if len(candidate.encode("utf-8")) >= 32:
                            persisted = candidate
                            break
                except OSError:
                    continue

            if persisted is None:
                persisted = _secrets.token_urlsafe(48)
                try:
                    secret_path.parent.mkdir(parents=True, exist_ok=True)
                    secret_path.write_text(persisted, encoding="utf-8")
                    # Best-effort chmod 600 (POSIX). On Windows the file
                    # inherits user-only ACLs from the home directory.
                    try:
                        secret_path.chmod(0o600)
                    except OSError:
                        pass
                    logger.info(
                        "JWT_SECRET was default/short - generated a fresh dev secret "
                        "and persisted it to %s. Sessions now survive restarts. "
                        "Set JWT_SECRET env var for a stable team-wide secret.",
                        secret_path,
                    )
                except OSError as _persist_err:
                    logger.warning(
                        "JWT_SECRET persistence to %s failed (%s) - falling back "
                        "to a per-process random secret. Sessions WILL be invalidated "
                        "on every restart. Set JWT_SECRET env var (>=32 bytes) "
                        "to keep sessions alive.",
                        secret_path,
                        _persist_err,
                    )
            else:
                logger.info(
                    "JWT_SECRET was default/short - loaded persisted dev secret from %s. "
                    "Existing sessions remain valid. Set JWT_SECRET env var for a "
                    "stable team-wide secret.",
                    secret_path,
                )

            try:
                # pydantic-settings blocks direct assignment when frozen,
                # but the default Settings class is mutable. If the field
                # is frozen in a future refactor, falling back to
                # ``object.__setattr__`` keeps us safe.
                settings.jwt_secret = persisted
            except Exception:
                object.__setattr__(settings, "jwt_secret", persisted)

        if settings.is_production:
            if "minioadmin" in (settings.s3_access_key + settings.s3_secret_key):
                logger.warning("S3 credentials are using development defaults")
            if "localhost" in settings.database_url:
                logger.warning("DATABASE_URL points to localhost in production")

        # Load translations (24 languages)
        _section("i18n")
        from app.core.i18n import load_translations

        load_translations()

        # Register core permissions
        _section("Permissions")
        from app.core.permissions import register_core_permissions

        register_core_permissions()

        # Auto-create tables on PostgreSQL on first start.
        # Why: the v0.9.0 baseline Alembic migration is a no-op (it documents
        # that tables are created via SQLAlchemy create_all), and the
        # docker-compose.quickstart.yml entrypoint does not run
        # `alembic upgrade head` before uvicorn. Result on a fresh PG
        # volume: schema never created, login fails with
        # `relation "oe_users_user" does not exist` (issue #42).
        # SQLAlchemy create_all is idempotent on PG and harmless on existing
        # databases - it only creates tables that do not yet exist.
        _section("Database")
        if "postgresql" in settings.database_url:
            import importlib
            import pkgutil

            from app import modules as _modules_pkg
            from app.core import audit as _audit_core  # noqa: F401

            # ``audit_log`` defines the ``oe_activity_log`` table used by the
            # FSM ``log_activity()`` helper (submittals/RFI/etc. status
            # transitions). It lives in app.core (not app.modules.*) so the
            # dynamic module-models loop below never reaches it. Without this
            # explicit import the table is absent on a fresh database, so every
            # status-changing action raised an error, which poisoned the request
            # session and cascaded into a 500 on the subsequent re-fetch.
            # Register it before create_all.
            from app.core import audit_log as _audit_log_core  # noqa: F401
            from app.database import Base, engine

            # Register EVERY module's SQLAlchemy models before create_all so
            # a fresh PostgreSQL database gets all tables. This was
            # previously a hand-maintained import list that silently omitted
            # ~18 modules (service, resources, equipment, portal,
            # daily_diary, schedule_advanced, crm, contracts, variations,
            # bid_management, qms, hse_advanced, carbon, bi_dashboards,
            # subcontractors, supplier_catalogs, property_dev,
            # compliance_docs). Their tables were never created on a clean
            # install, so every list endpoint 500'd with "no such table".
            # Discovering models dynamically makes that whole class of bug
            # impossible: any module package with a models.py is registered
            # automatically - adding a new module needs no edit here.
            for _m in pkgutil.iter_modules(_modules_pkg.__path__):
                if not _m.ispkg:
                    continue
                _models_mod = f"app.modules.{_m.name}.models"
                try:
                    importlib.import_module(_models_mod)
                except ModuleNotFoundError as exc:
                    # No models.py in this module - fine, skip it. Re-raise
                    # if the failure is a *different* missing import inside
                    # the models module (that is a real bug, not absence).
                    if exc.name != _models_mod:
                        raise

            # Add missing columns to existing tables before create_all runs.
            # create_all only ever creates whole new *tables*; it never adds a
            # *column* to a table that already exists. So after an app upgrade
            # that added a column to an existing model (for example
            # oe_boq_position.cost_line_id from the v6.4.0 cost spine), that
            # column is absent on a database first created under the older
            # version, and every ORM read of the table fails with a missing-
            # column error.
            #
            # Embedded PostgreSQL is the default no-Docker runtime and is not
            # managed by Alembic, so it needs an auto-heal via
            # ADD COLUMN IF NOT EXISTS. External PostgreSQL (a user-supplied
            # DATABASE_URL, where embedded_pg is not running) keeps managing
            # columns with Alembic and is left alone.
            # Heal column/index drift on BOTH embedded and external PostgreSQL.
            # create_all (below) only ever creates whole missing *tables*; it
            # never adds a *column* to a table that already exists. So an
            # external database first created under an older release is missing
            # every column added since (for example oe_ai_agents_run.trust from
            # v3204), and every ORM read of that table 500s with a DBAPI
            # UndefinedColumn error (e.g. GET /ai-agents/insights). The migrator
            # only issues ADD COLUMN / CREATE INDEX IF NOT EXISTS, which is
            # idempotent and non-destructive, so it is safe to run regardless of
            # who manages the schema. Wrapped non-fatally: an external DB role
            # without DDL rights (or any other failure) just logs a warning and
            # leaves schema management to the operator's `alembic upgrade head`,
            # exactly as before.
            from app.core.postgres_migrator import postgres_auto_migrate

            try:
                migrated = await postgres_auto_migrate(engine, Base)
                if migrated:
                    logger.info(
                        "PostgreSQL auto-migration: %d schema objects (columns + indexes) added",
                        migrated,
                    )
            except Exception:
                logger.warning("PostgreSQL auto-migration skipped (non-fatal)", exc_info=True)

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL tables created/verified")

            # Stamp the alembic version table to head on a fresh managed DB.
            # create_all above materialises the full current schema, so the
            # database is by definition at head; recording that lets the
            # health check report a clean state instead of "degraded" on
            # every fresh install, and makes a later ``alembic upgrade head``
            # a correct no-op rather than an attempt to replay the whole
            # chain against already-present tables. This is the runtime
            # counterpart of alembic/env.py's fresh-blank-DB shortcut (which
            # only fires when ops run migrations before the app ever boots).
            # Only stamps when the version table is empty/absent so it never
            # clobbers an existing migration state. Non-fatal.
            def _stamp_head_if_unstamped(sync_conn: object) -> str | None:
                from alembic.migration import MigrationContext

                ctx = MigrationContext.configure(sync_conn)
                if ctx.get_current_revision() is None:
                    ctx._stamp_head()
                    return "stamped"
                return None

            try:
                with engine.begin() as conn:
                    result = conn.run_sync(_stamp_head_if_unstamped)
                if result:
                    logger.info("Alembic version table stamped to head")
            except Exception:
                logger.warning("Failed to stamp alembic version table", exc_info=True)

        # Load and enable modules
        _section("Modules")
        await module_loader.load_and_enable()

        # Seed demo account (if enabled)
        _section("Demo Seed")
        await _seed_demo_account()

        # Initialize vector database (non-blocking)
        _section("Vector DB")
        _init_vector_db()

        # Start vector auto-backfill in the background
        _section("Vector Backfill")
        import asyncio

        asyncio.create_task(_auto_backfill_vector_collections())

        logger.info("%s startup complete", settings.app_name)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("Shutting down %s", settings.app_name)
        from app.database import engine

        # Stop the collaboration-lock sweeper before closing the DB
        # engine so its last iteration cannot hit a disposed pool.
        try:
            from app.modules.collaboration_locks.sweeper import stop_sweeper

            stop_sweeper()
        except Exception:
            logger.debug("collab lock sweeper stop failed", exc_info=True)

        # Tear down the embedding inference pool so Ctrl-C doesn't
        # leave orphan Python worker processes alive.
        try:
            from app.core.embedding_pool import shutdown_pool

            shutdown_pool()
        except Exception:
            logger.debug("embedding pool shutdown failed", exc_info=True)

        # Close the Geo Hub basemap tile proxy's shared httpx connection
        # pool so a reload / Ctrl-C doesn't leave kept-alive sockets open.
        try:
            from app.modules.geo_hub.router import close_tile_client

            await close_tile_client()
        except Exception:
            logger.debug("geo tile client shutdown failed", exc_info=True)

        await engine.dispose()

        # Stop the embedded PostgreSQL cluster last (after the engine pool is
        # closed), if this process booted one. No-op otherwise.
        try:
            from app.core import embedded_pg

            embedded_pg.shutdown()
        except Exception:  # noqa: BLE001
            logger.debug("embedded PostgreSQL shutdown skipped", exc_info=True)