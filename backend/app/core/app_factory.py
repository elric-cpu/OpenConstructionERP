# OpenConstructionERP - DataDrivenConstruction (DDC)
# CWICR Cost Database Engine · CAD2DATA Pipeline
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
# AGPL-3.0 License · DDC-CWICR-OE-2026
"""Application factory.

Creates and configures the FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config.settings import get_settings
from app.core.app_lifecycle import setup_app_lifecycle
from app.core.system_router import router as system_router


def create_app() -> FastAPI:
    """Application factory.

    Creates and configures the FastAPI application:
    1. Load settings
    2. Configure logging
    3. Create FastAPI instance
    4. Add middleware
    5. Add exception handlers
    6. Mount routers (including system routes)
    7. Setup application lifecycle (startup/shutdown)
    """
    settings = get_settings()
    # Note: configure_logging is called in setup_app_lifecycle to ensure
    # logging is configured before any logging occurs in startup.
    # However, we need to configure logging early for middleware and startup.
    # We'll keep it here for now, but note that setup_app_lifecycle also calls it.
    # To avoid double configuration, we'll adjust later.
    from app.core.app_lifecycle import configure_logging

    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Open-source modular platform for construction cost estimation",
        contact={
            "name": "DataDrivenConstruction · OpenConstructionERP",
            "url": "https://openconstructionerp.com",
            "email": "info@datadrivenconstruction.io",
        },
        license_info={
            "name": "AGPL-3.0-or-later · DDC-CWICR-OE-2026",
            "url": "https://www.gnu.org/licenses/agpl-3.0.html",
        },
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        # BUG-394: don't expose the full OpenAPI schema in production - it
        # hands attackers a route/parameter enumeration map of every endpoint,
        # including rarely-exercised admin surfaces. Dev still gets it for
        # the Swagger/ReDoc UI and for openapi-typescript client generation.
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        swagger_ui_oauth2_redirect_url=("/api/docs/oauth2-redirect" if not settings.is_production else None),
        redirect_slashes=False,
        # NOTE: do NOT set default_response_class=ORJSONResponse here.
        # FastAPI's own deprecation warning explains why: "FastAPI now
        # serializes data directly to JSON bytes via Pydantic when a
        # return type or response model is set, which is faster and
        # doesn't need a custom response class." More importantly,
        # orjson rejects NaN/Infinity floats by default - DDC cad2data
        # BIM elements occasionally emit NaN bbox coordinates for
        # degenerate geometry, which would 500 the response. Stick with
        # FastAPI's default Pydantic-direct path; orjson is still used
        # by handlers that explicitly opt in.
    )

    # ── OpenAPI origin extension ─────────────────────────────────────────
    # Stamp an x- vendor extension into info{} so any fork that exposes
    # /api/openapi.json or /api/docs leaks provenance. ``x-`` extensions
    # are valid per the OpenAPI spec and ignored by every generator /
    # client (incl. openapi-typescript), so the API surface is unchanged.
    # The token bytes XOR-decode (key 0x55) to the authorship marker.
    from fastapi.openapi.utils import get_openapi as _get_openapi

    def _custom_openapi() -> dict[str, any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = _get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            contact=app.contact,
            license_info=app.license_info,
        )
        _oa_tok = bytes(
            b ^ 0x55 for b in b"\x11\x11\x16\x78\x16\x02\x1c\x16\x07\x78\x1a\x10\x78\x67\x65\x67\x63"
        ).decode("ascii")
        schema.setdefault("info", {})
        schema["info"]["x-ddc-origin"] = "OpenConstructionERP · DataDrivenConstruction · " + _oa_tok
        schema["info"]["x-ddc-author"] = "Artem Boiko <info@datadrivenconstruction.io>"
        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]

    # ── Middleware ───────────────────────────────────────────────────────
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import Response as StarletteResponse

    cors_origins = settings.cors_origins
    # Security: block wildcard origins in production
    if settings.is_production and "*" in cors_origins:
        logger.warning(
            "CORS: wildcard '*' origin is not allowed in production. Set ALLOWED_ORIGINS to your actual domain(s)."
        )
        cors_origins = [o for o in cors_origins if o != ""]
        if not cors_origins:
            cors_origins = ["https://openconstructionerp.com"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept", "Accept-Language"],
    )

    # ── API Version header ──────────────────────────────────────────────
    class APIVersionMiddleware(BaseHTTPMiddleware):
        """Add X-API-Version response header to every API response."""

        async def dispatch(self, request: StarletteRequest, call_next):  # noqa: ANN001, ANN201
            response: StarletteResponse = await call_next(request)
            response.headers["X-API-Version"] = settings.app_version
            return response

    app.add_middleware(APIVersionMiddleware)

    # ── Reject non-finite floats in JSON request bodies ─────────────────
    # Python's ``json`` decoder accepts the non-standard ``NaN`` / ``Infinity``
    # literals by default. Several handlers use those values in Decimal
    # arithmetic downstream and raise ``decimal.InvalidOperation`` → 500.
    # We refuse them up-front with 422 so clients get a deterministic error
    # and Pydantic validators still see finite numbers.
    import re as _re

    import orjson as _orjson
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    _NONFINITE_TOKEN_RE = _re.compile(rb"\b(NaN|-?Infinity)\b")

    class _RejectNonFiniteJSONMiddleware:
        """Pure-ASGI middleware so we can rewrite the receive() stream."""

        def __init__(self, app: ASGIApp) -> None:
            self.inner = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope.get("type") != "http":
                await self.inner(scope, receive, send)
                return
            method = scope.get("method", "").upper()
            if method not in ("POST", "PUT", "PATCH"):
                await self.inner(scope, receive, send)
                return
            headers = dict(scope.get("headers") or [])
            content_type = headers.get(b"content-type", b"").decode("latin-1", "ignore")
            if "application/json" not in content_type.lower():
                await self.inner(scope, receive, send)
                return

            # Drain body up-front so we can scan it AND replay it to the app.
            body = bytearray()
            more = True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    await self.inner(scope, receive, send)
                    return
                body.extend(message.get("body") or b"")
                more = message.get("more_body", False)

            if _NONFINITE_TOKEN_RE.search(bytes(body)):
                # Extra safety: confirm the tokens occur outside a string literal
                # before rejecting. ``orjson`` rejects non-finite floats by
                # default, so parsing failure with the token present = real
                # non-finite number.
                try:
                    _orjson.loads(bytes(body))
                except _orjson.JSONDecodeError:
                    from starlette.responses import JSONResponse

                    resp = JSONResponse(
                        status_code=422,
                        content={"detail": ("NaN and Infinity are not accepted in numeric fields")},
                    )
                    await resp(scope, receive, send)
                    return

            sent = False

            async def replay() -> Message:
                # First call: hand the app the fully buffered body. Every
                # subsequent call must delegate to the *real* receive() - it
                # MUST NOT synthesize ``http.disconnect`` here. Streaming
                # responses (SSE: /erp_chat/stream/, AI chat) run
                # ``listen_for_disconnect`` concurrently with the body
                # generator under Starlette's StreamingResponse; a premature
                # fake ``http.disconnect`` made that watcher return instantly
                # and cancel the stream before a single byte was sent (the
                # endpoint returned HTTP 200 with a 0-byte body). Forwarding
                # the genuine receive() preserves real client-disconnect
                # detection without killing live streams.
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.inner(scope, replay, send)

    app.add_middleware(_RejectNonFiniteJSONMiddleware)

    # ── DDC Fingerprint ──────────────────────────────────────────────────
    from app.middleware.fingerprint import DDCFingerprintMiddleware

    app.add_middleware(DDCFingerprintMiddleware)

    # ── Security headers (X-Frame-Options, CSP, HSTS, etc.) ──────────────
    from app.middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

    # ── Request correlation ID (must precede SlowRequestLogger so its log
    # lines carry the ID via the RequestIDLogFilter context) ───────────────
    # ── Universal audit capture context (Epic H) ──────────────────────────
    # Sets the per-request AuditContext ContextVar so :func:`log_activity`
    # can persist the peer IP, User-Agent, and correlation ID without
    # service-layer callers having to thread the values manually.
    # Starlette runs middleware in REVERSE registration order - the
    # ``add_middleware(RequestIDMiddleware)`` call below must come AFTER
    # this one so the request-id ContextVar is set BEFORE
    # ActorContextMiddleware reads it via ``get_request_id()``.
    from app.middleware.actor_context import ActorContextMiddleware
    from app.middleware.request_id import RequestIDMiddleware

    app.add_middleware(ActorContextMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Slow request logger (warns on > 500ms responses) ──────────────────
    from app.middleware.slow_request_logger import SlowRequestLoggerMiddleware

    app.add_middleware(SlowRequestLoggerMiddleware)

    # ── Accept-Language (sets i18n context locale per request) ────────────
    from app.middleware.accept_language import AcceptLanguageMiddleware

    app.add_middleware(AcceptLanguageMiddleware)

    # ── Request-body-size backstop (added last -> outermost -> runs first) ─
    # Coarse global ceiling above every per-endpoint upload cap. Rejects an
    # absurdly large body before any other middleware or endpoint reads it, so
    # a single oversized request can't OOM the worker. Per-endpoint caps remain
    # the fine-grained defense.
    from app.middleware.body_size_limit import MaxBodySizeMiddleware

    app.add_middleware(MaxBodySizeMiddleware, max_body_bytes=settings.max_request_body_bytes)

    # ── Global exception handler - return JSON for unhandled errors ────
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    from app.middleware.request_id import get_request_id

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Surface the SAME correlation id the RequestIDMiddleware already
        # assigned (and echoed on the X-Request-ID response header) - do NOT
        # mint a new one. A client / support engineer can quote this id and we
        # can find the matching ``logger.exception`` line below in the server
        # logs (the RequestIDLogFilter tags every record with it). The full
        # stack trace stays server-side; the client only ever sees the opaque
        # id, never the exception text.
        request_id = get_request_id()
        logger.exception(
            "Unhandled exception on %s %s (request_id=%s)",
            request.method,
            request.url.path,
            request_id or "-",
        )
        body: dict[str, str] = {"detail": "Internal server error"}
        if request_id:
            body["request_id"] = request_id
        response = JSONResponse(status_code=500, content=body)
        # The exception path bypasses the RequestIDMiddleware's normal
        # response-header injection (the middleware's call_next raised), so
        # re-attach the header here for trace correlation parity.
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    # BUG-API02: sanitise FastAPI's default RequestValidationError response.
    #
    # Out of the box FastAPI returns 422 with a body that exposes the path
    # parameter name and its expected Pydantic type, e.g.
    #   {"detail":[{"type":"uuid_parsing","loc":["path","user_id"],"input":"abc"}]}
    # An unauthenticated probe can read those bodies to enumerate the route
    # surface (param names + types). For path-param validation failures -
    # which mostly mean "the URL was malformed" - we collapse the response
    # to a generic 400 with no schema details.
    #
    # Body / query-param validation errors keep the legacy 422 + detail
    # behaviour because those are real client-error feedback (e.g. POST
    # /users/ with role="god" must surface "role: invalid value" so the
    # admin UI can show a useful message).  When ``app_debug`` is on, the
    # full Pydantic detail is preserved everywhere so developers can still
    # see what they broke.
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        path_only = bool(errors) and all((err.get("loc") or [None])[0] == "path" for err in errors)

        if path_only and not settings.app_debug:
            # No detail leak - just acknowledge the URL is malformed.
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid request"},
            )

        # Body / query / header validation: keep informative detail so
        # client UIs can render per-field errors.  In production we still
        # strip the raw input echo (Pydantic includes the offending value
        # in ``input`` which can echo PII / tokens).
        # ``ctx.error`` is a raw ``ValueError`` instance for ``value_error``
        # entries - not JSON-serialisable - so always coerce to ``str``
        # before emitting (regression seen with custom ``field_validator``
        # raises in BUG-MATH03 unit-catalogue checks).
        def _json_safe(v: object) -> object:
            if isinstance(v, (str, int, float, bool, type(None))):
                return v
            if isinstance(v, (list, tuple)):
                return [_json_safe(x) for x in v]
            if isinstance(v, dict):
                return {str(k): _json_safe(x) for k, x in v.items()}
            return str(v)

        def _scrub(err: dict) -> dict:
            return _json_safe(dict(err))

        if settings.app_debug:
            safe_errors = [_scrub(e) for e in errors]
        else:
            safe_errors = [{k: v for k, v in _scrub(err).items() if k != "input"} for err in errors]
        return JSONResponse(
            status_code=422,
            content={"detail": safe_errors},
        )

    # ── System Routes ───────────────────────────────────────────────────
    app.include_router(system_router, prefix="/api")

    # Desktop first-run / bootstrap auth endpoints. The users module router is
    # auto-mounted by the loader at /api/v1/users, but the desktop shell needs
    # a short app-level path it can call without knowing the module mount, so
    # these two routes are mounted explicitly at /api/v1/auth/
    from app.modules.users.router import desktop_auth_router

    app.include_router(desktop_auth_router, prefix="/api/v1/auth")

    # Workspace white-label branding. GET is public (the login page reads it
    # before sign-in so invited users see the workspace brand); PUT/DELETE are
    # admin-only. Persisted to a JSON file in the data dir, so no migration.
    from app.core.branding_router import router as branding_router

    app.include_router(branding_router, prefix="/api/v1")

    # Module management API (list / enable / disable)
    from app.core.module_router import router as module_mgmt_router

    app.include_router(module_mgmt_router)

    # Audit log API (admin-only)
    from app.core.audit_router import router as audit_router

    app.include_router(audit_router)

    # Global search API (cross-module)
    from app.core.global_search_router import router as search_router

    app.include_router(search_router)

    # Activity feed API (cross-module)
    from app.core.activity_feed_router import router as activity_router

    app.include_router(activity_router)

    # Sidebar badge counts (single endpoint for Tasks + RFI + Safety counts)
    from app.core.sidebar_badges_router import router as sidebar_badges_router

    app.include_router(sidebar_badges_router)

    # Translation service (element → catalog cross-lingual normalisation)
    from app.core.translation.router import router as translation_router

    app.include_router(translation_router, prefix="/api/v1")

    # Partner-pack system - discovers pip-installed packs via entry_points
    # and exposes the active manifest + branded resources.
    from app.core.partner_pack.discovery import get_active_pack
    from app.core.partner_pack.router import alias_router as packs_alias_router
    from app.core.partner_pack.router import router as partner_pack_router

    app.include_router(partner_pack_router)
    # Canonical Packs-umbrella alias (/api/v1/packs/*) sharing the same handlers.
    app.include_router(packs_alias_router)
    _active_pack = get_active_pack()
    if _active_pack:
        logger.info(
            "Partner pack active: %s (%s) v%s",
            _active_pack.slug,
            _active_pack.partner_name,
            _active_pack.pack_version,
        )

    # Setup application lifecycle (startup/shutdown)
    setup_app_lifecycle(app)

    return app