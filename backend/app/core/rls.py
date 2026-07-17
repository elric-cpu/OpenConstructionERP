# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Row-level-security tenant plumbing (default OFF).

PostgreSQL row-level security is the backstop under the app-layer tenant
guards: even if a query forgets its ``tenant_id`` filter, the database refuses
to return or change another tenant's rows. It is enforced only when
``settings.rls_enforce`` is True AND the request connects through a
non-superuser role, because a superuser (and, without ``FORCE``, a table owner)
bypasses every policy. Both conditions are opt-in, so this module is inert on a
default install: the flag is False and the app connects as the cluster
superuser, exactly as before.

Mechanism, when enabled:

* A per-request :class:`~contextvars.ContextVar` carries the caller's tenant id.
  It is bound at the top of a request by ``rls_request_context`` (wired in
  ``app.dependencies``) and cleared when the request ends.
* An ``after_begin`` listener on the request session stamps a transaction-local
  ``app.current_tenant`` GUC from that ContextVar every time a transaction
  starts, so it survives mid-request commits. The policies read it via
  ``current_setting('app.current_tenant', true)``.
* A session with no tenant in context (a background job, the event bus, a seed)
  leaves the GUC unset; a fail-closed policy then matches no rows, which is why
  such out-of-request sessions must run under the BYPASSRLS system role.

This module is deliberately import-light (only SQLAlchemy + settings) so it can
be imported from the database layer without a dependency cycle.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar, Token
from typing import Final

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

# The PostgreSQL run-time parameter the tenant policies read. A dotted,
# app-namespaced name is required for a custom GUC (a bare name is rejected by
# PostgreSQL as an unrecognised configuration parameter).
GUC_NAME: Final[str] = "app.current_tenant"

# Per-request tenant id, bound at request entry and read when a transaction
# begins. Default None => "no tenant" => a fail-closed policy denies the
# session, so background/out-of-request work must use the BYPASSRLS role.
_request_tenant: ContextVar[str | None] = ContextVar("rls_request_tenant", default=None)

# Guards one-time listener registration so a re-import (or a test that rebuilds
# the engine) does not stack duplicate listeners on the same Session class.
_installed: set[int] = set()


def rls_enabled() -> bool:
    """Return True when row-level-security enforcement is switched on.

    Reads the cached settings singleton. Never raises: a settings hiccup
    degrades to "disabled" so a misconfiguration cannot wedge every query.
    """
    try:
        return bool(get_settings().rls_enforce)
    except Exception:  # noqa: BLE001 - a query must never die on a settings read
        return False


def set_request_tenant(tenant_id: str | None) -> Token[str | None]:
    """Bind ``tenant_id`` to the current async context.

    Returns the reset token; pass it to :func:`reset_request_tenant` in a
    ``finally`` so the binding never leaks to the next request served on the
    same worker task.
    """
    return _request_tenant.set(tenant_id)


def reset_request_tenant(token: Token[str | None]) -> None:
    """Undo a :func:`set_request_tenant`, tolerating a stale/foreign token."""
    with contextlib.suppress(ValueError, LookupError):
        _request_tenant.reset(token)


def current_request_tenant() -> str | None:
    """Return the tenant id bound to this context, or None."""
    return _request_tenant.get()


def _apply_tenant_guc(connection, tenant_id: str) -> None:  # noqa: ANN001 - SA connection
    """Set the transaction-local tenant GUC on a live connection.

    Uses ``set_config(name, value, is_local => true)`` so the value is scoped
    to the current transaction and reset on commit/rollback; the
    ``after_begin`` listener re-applies it on the next transaction.
    """
    connection.execute(
        text("SELECT set_config(:name, :val, true)"),
        {"name": GUC_NAME, "val": tenant_id},
    )


def install(session_class: type[Session]) -> None:
    """Register the ``after_begin`` GUC-stamping listener on ``session_class``.

    Attach to the sync ``Session`` class underlying the async session factory.
    The listener is a no-op while the flag is off (one function call + a cached
    bool read), so the default path is effectively free. Idempotent: registering
    the same class twice is ignored.
    """
    key = id(session_class)
    if key in _installed:
        return
    _installed.add(key)

    @event.listens_for(session_class, "after_begin")
    def _stamp_tenant_guc(session, transaction, connection) -> None:  # noqa: ANN001, ARG001
        if not rls_enabled():
            return
        tenant_id = _request_tenant.get()
        if tenant_id is None:
            # Background/system session: leave the GUC unset. A fail-closed
            # policy denies it; it must run under the BYPASSRLS system role.
            return
        # If stamping the GUC fails we must NOT proceed - running the query
        # without the tenant scope would either leak or, under a fail-closed
        # policy, silently return nothing. Raise so the request fails loudly.
        _apply_tenant_guc(connection, tenant_id)
