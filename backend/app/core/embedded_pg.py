"""Optional embedded PostgreSQL runtime — a real PG16 in-process, no Docker.

Boots a PostgreSQL 16 cluster from the ``pixeltable-pgserver`` wheel (bundled PG
binaries) and points the app's ``DATABASE_URL`` / ``DATABASE_SYNC_URL`` at it, so
the whole app runs on PostgreSQL with zero external setup. Opt-in only:

* ``openconstructionerp serve --embedded-pg``  (sets ``OE_USE_EMBEDDED_PG=1``), or
* ``OE_USE_EMBEDDED_PG=1`` in the environment (honoured by every CLI command).

The cluster's data directory is ``<data_dir>/pgdata`` so it survives restarts.
On first boot ``initdb`` runs once (a few seconds); subsequent boots attach to the
existing cluster.

Ordering contract
~~~~~~~~~~~~~~~~~
``app.database`` builds the SQLAlchemy engine from ``settings.database_url`` at
*import time*. :func:`boot` therefore MUST run before the first ``from app...``
import that pulls in ``app.database`` (and before ``get_settings()`` is cached).
The CLI calls it from ``_setup_env``, which every command runs before importing
any app module — so the contract holds for ``serve``/``init-db``/``seed``.

Single-process only: run ONE uvicorn worker with embedded PG (the default). For
multi-worker deployments use an external PostgreSQL and set ``DATABASE_URL``
directly.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: Module-level handle to the running server, kept so :func:`shutdown` can stop it.
_server = None

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def is_requested() -> bool:
    """True when the app should run on the embedded PostgreSQL cluster.

    As of v6.0.0 embedded PostgreSQL is the **default** runtime — a fresh
    ``openconstructionerp serve`` boots a real in-process PG16 (no Docker). The
    operator opts out in any of three ways, checked in order:

    * ``OE_USE_SQLITE`` truthy — keep the legacy single-file SQLite database
      (the documented escape hatch while PostgreSQL is proven in production);
    * an explicit ``DATABASE_URL`` in the environment — "use my own database",
      so we never override it with an embedded cluster;
    * ``OE_USE_EMBEDDED_PG`` set to a falsy value (``0``/``false``/``no``/``off``)
      — explicit opt-out without switching to SQLite (e.g. an external PG set
      via ``DATABASE_URL`` is also covered by the rule above).

    Otherwise (the default, and any truthy ``OE_USE_EMBEDDED_PG``) it returns
    ``True``. An explicit truthy ``OE_USE_EMBEDDED_PG`` wins over an ambient
    ``DATABASE_URL`` (the two together are contradictory; the explicit flag is
    the clearer intent).
    """
    explicit = os.environ.get("OE_USE_EMBEDDED_PG", "").strip().lower()
    if os.environ.get("OE_USE_SQLITE", "").strip().lower() in _TRUTHY:
        return False
    if explicit in _TRUTHY:
        return True
    if os.environ.get("DATABASE_URL", "").strip():
        return False
    if explicit in _FALSY:
        return False
    return True


def is_running() -> bool:
    """True once :func:`boot` has successfully started a cluster this process."""
    return _server is not None


def boot(data_dir: Path | str) -> bool:
    """Boot embedded PostgreSQL and point DATABASE_URL/DATABASE_SYNC_URL at it.

    Idempotent (a second call is a no-op once running). Never raises: on any
    failure it logs and returns ``False``, leaving the existing (SQLite) URLs in
    place so the app can still come up. Returns ``True`` on success.
    """
    global _server
    if _server is not None:
        return True

    try:
        import pixeltable_pgserver as pgserver
        from sqlalchemy.engine import make_url
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "embedded PostgreSQL requested but pixeltable-pgserver is not installed "
            "(pip install 'openconstructionerp[server]' or pixeltable-pgserver): %r",
            exc,
        )
        return False

    pgdata = Path(data_dir).expanduser() / "pgdata"
    try:
        pgdata.mkdir(parents=True, exist_ok=True)
        srv = pgserver.get_server(str(pgdata))
    except Exception as exc:  # noqa: BLE001
        logger.error("embedded PostgreSQL failed to start at %s: %r", pgdata, exc)
        return False

    try:
        # get_uri() is portable: TCP loopback on Windows, a unix socket on
        # Linux/macOS. Swap only the SQLAlchemy driver — never hand-parse it.
        base = make_url(srv.get_uri())
        async_url = base.set(drivername="postgresql+asyncpg")
        sync_url = base.set(drivername="postgresql+psycopg2")
        os.environ["DATABASE_URL"] = async_url.render_as_string(hide_password=False)
        os.environ["DATABASE_SYNC_URL"] = sync_url.render_as_string(hide_password=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("embedded PostgreSQL booted but URL wiring failed: %r", exc)
        try:
            srv.cleanup()
        except Exception:  # noqa: BLE001
            pass
        return False

    _server = srv
    logger.info("embedded PostgreSQL ready (data dir: %s)", pgdata)
    return True


def auto_migrate_legacy_sqlite(data_dir: Path | str) -> str:
    """One-time transparent SQLite -> embedded-PostgreSQL data migration.

    Runs only when ALL hold: embedded PG is running, a legacy
    ``<data_dir>/openestimate.db`` exists with content, the target is PostgreSQL,
    and the embedded cluster has no app rows yet (so an already-populated PG is
    never clobbered). On success the SQLite file is renamed to
    ``openestimate.db.migrated`` (with a numeric suffix if needed) so it never
    re-runs. Never raises -- returns a human-readable status string for the
    caller to log/print. A no-op (and safe) when the preconditions don't hold.
    """
    if _server is None:
        return "skip: embedded PostgreSQL not running"

    sqlite_file = Path(data_dir).expanduser() / "openestimate.db"
    try:
        if not sqlite_file.exists() or sqlite_file.stat().st_size == 0:
            return "skip: no legacy SQLite database to migrate"
    except OSError as exc:
        return f"skip: cannot stat {sqlite_file}: {exc!r}"

    sync_url = os.environ.get("DATABASE_SYNC_URL", "")
    if "postgresql" not in sync_url:
        return "skip: target is not PostgreSQL"

    try:
        from sqlalchemy import create_engine

        from app.scripts import migrate_sqlite_to_postgres as migrator
    except Exception as exc:  # noqa: BLE001
        logger.error("auto-migration unavailable: %r", exc)
        return f"error: migration module import failed: {exc!r}"

    dst = None
    src = None
    try:
        base = migrator._load_metadata()
        dst = create_engine(sync_url)
        base.metadata.create_all(dst)

        existing = migrator._target_has_rows(dst, base)
        if existing:
            return f"skip: embedded PostgreSQL already has data (e.g. '{existing}')"

        src = migrator._make_source_engine(f"sqlite:///{sqlite_file.as_posix()}")
        skipped = migrator._copy_all(src, dst, base, 1000)
        migrator._reset_sequences(dst, base)
    except Exception as exc:  # noqa: BLE001
        logger.exception("SQLite -> PostgreSQL auto-migration failed")
        return f"error: {exc!r}"
    finally:
        for eng in (src, dst):
            if eng is not None:
                try:
                    eng.dispose()
                except Exception:  # noqa: BLE001
                    pass

    # Rename the source so a later boot does not migrate again.
    backup = sqlite_file.with_name(sqlite_file.name + ".migrated")
    counter = 0
    while backup.exists():
        counter += 1
        backup = sqlite_file.with_name(f"{sqlite_file.name}.migrated.{counter}")
    try:
        sqlite_file.rename(backup)
        kept = backup.name
    except OSError:
        logger.warning("migrated but could not rename %s", sqlite_file)
        kept = sqlite_file.name + " (rename failed)"

    msg = (
        f"migrated SQLite -> embedded PostgreSQL "
        f"(skipped {skipped} unconvertible rows); legacy db kept as {kept}"
    )
    logger.info(msg)
    return msg


def shutdown() -> None:
    """Stop the embedded cluster if this process booted one (safe to always call)."""
    global _server
    if _server is None:
        return
    try:
        _server.cleanup()
        logger.info("embedded PostgreSQL stopped")
    except Exception:  # noqa: BLE001
        logger.debug("embedded PostgreSQL cleanup failed", exc_info=True)
    finally:
        _server = None
