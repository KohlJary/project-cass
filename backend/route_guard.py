"""
Route guard: one app-wide auth dependency, default-deny.

Why: the server binds 0.0.0.0 and each router used to opt in to auth on its
own, so most of the API (files, terminal, git, export, admin sub-routers,
GraphQL...) was open to anyone who could reach the port.

How it works:
  - main_sdk.py creates the app with dependencies=[Depends(route_guard)], so
    this runs before every HTTP route and WebSocket route.
  - classify_routes(app) runs once after all routes are mounted and gives
    every endpoint a level:
        public  - no auth (login, health, SPA, media loaded by <img>/<audio>)
        user    - any authenticated user
        self    - the route declares its own auth dependency; leave it alone
        admin   - everything else (the default, including any route added later)
  - The /admin area is admin-only: every /admin/* route is ADMIN level unless
    it is public or listed in ADMIN_AREA_USER_ROUTES, whatever auth dependency
    the handler declares. (Many admin handlers declare require_auth, which
    accepts any dashboard user, admin or not.)
  - "Authenticated" means: an access token accepted by
    auth.verify_access_token (the one token format, plus the two pre-#61
    formats until they expire), or the localhost bypass
    (ALLOW_LOCALHOST_BYPASS + DEFAULT_LOCALHOST_USER_ID) for genuinely-local,
    non-proxied, same-origin requests. Admin level then checks users.is_admin
    in SQLite, capped by the token's role claim (principal_is_admin).
  - WebSockets cannot send headers from a browser, so for them a ?token= query
    parameter is accepted too.
  - DEMO_MODE: anonymous callers get read-only access (GET/HEAD) to admin and
    user routes, except DANGEROUS_PREFIXES, which always need a real admin.
"""
import fnmatch
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, status
from fastapi.exceptions import WebSocketException
from starlette.requests import HTTPConnection

import config

PUBLIC = "public"
USER = "user"
SELF = "self"
ADMIN = "admin"

# (method, path template). Method "*" = any; "WS" = websocket route.
# Path templates use fnmatch, so "/cass/*" covers everything below /cass.
PUBLIC_ROUTES = [
    ("GET", "/health"),
    ("GET", "/"),
    ("GET", "/status"),
    # Login / token endpoints
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/refresh"),
    ("POST", "/admin/auth/login"),
    ("POST", "/admin/auth/register"),
    ("GET", "/admin/auth/status"),
    ("POST", "/admin/auth/bootstrap"),   # has its own one-time-token lockout
    # Published daemon homepages are meant to be public
    ("GET", "/admin/homepage/{daemon_label}/page/{page}"),
    # Loaded by <img>/<audio> tags, which cannot send an Authorization header.
    # Attachment ids are random uuid4 hex.
    ("GET", "/attachments/{attachment_id}"),
    ("GET", "/music/audio/{filename}"),
    # SPA catch-all (serves index.html when the admin frontend is built)
    ("GET", "/{full_path:path}"),
]

# The only /admin/* routes a non-admin may call (see ADMIN_AREA). Everything
# else under /admin is admin-only. Taken from what the admin frontend's
# non-admin pages call (api/domains/*.ts), plus the smart speaker. Listed
# routes that declare their own auth (require_auth) stay SELF; the rest are
# USER. Routes that take a user id check ownership in the handler.
ADMIN_AREA_USER_ROUTES = [
    # Every page: DaemonContext's daemon picker for non-admins (own daemons + Cass)
    ("GET", "/admin/daemons/mine"),
    # Genesis page (GenesisDream.tsx, GenesisNotification.tsx); handlers act
    # on the caller's own session only
    ("GET", "/admin/genesis/active"),
    ("POST", "/admin/genesis/start"),
    ("POST", "/admin/genesis/{session_id}/message"),
    ("POST", "/admin/genesis/{session_id}/complete"),
    ("POST", "/admin/genesis/{session_id}/abandon"),
    # Profile page (UserProfile.tsx); own user id only, any for admins
    ("GET", "/admin/users/{user_id}/model"),
    ("GET", "/admin/users/{user_id}/observations"),
    # Feedback page (Feedback.tsx); records the caller as the author
    ("POST", "/admin/feedback"),
    # Self-Development page tabs (Stakes, Consistency, Narration): reads of
    # Cass's self-model nodes. Their free-text fields may mention people.
    # Exact paths, so a new route here is admin-only until listed.
    ("GET", "/admin/self-model/stakes"),
    ("GET", "/admin/self-model/stakes/stats"),
    ("GET", "/admin/self-model/preference-tests"),
    ("GET", "/admin/self-model/preference-consistency"),
    ("GET", "/admin/self-model/narration-contexts"),
    ("GET", "/admin/self-model/narration-patterns"),
    # Smart speaker
    ("POST", "/admin/stt/transcribe"),
    ("GET", "/admin/stt/status"),
]

ADMIN_AREA = "/admin"

# Any logged-in user (not just admins). Taken from what the mobile app, the
# admin frontend's non-admin pages (Chat, Genesis, Self-Dev, Profile,
# Feedback), Godot and the smart speaker call.
USER_ROUTES = [
    ("POST", "/chat"),
    ("POST", "/attachments/upload"),
    ("DELETE", "/attachments/{attachment_id}"),
    ("GET", "/journal"),
    ("GET", "/journal/{date}"),
    # /users/{user_id}/journals* declare get_current_user (SELF level) and
    # check ownership themselves: own journals, or any for admins.
    ("POST", "/push/register"),
    ("DELETE", "/push/register"),
    ("GET", "/users/me/quiet-hours"),
    ("PUT", "/users/me/quiet-hours"),
    ("GET", "/cass/*"),                         # Self-Development page (reads)
    # /admin/* routes for non-admins are in ADMIN_AREA_USER_ROUTES, not here.
    ("GET", "/gestures/library"),
    ("POST", "/tts/generate"),                  # TUI voice playback
    ("GET", "/tts/config"),
    ("POST", "/api/ha/conversation"),           # Home Assistant integration
]

# Routes that do their own auth inside the handler (WebSocket message-level auth).
SELF_ROUTES = [
    ("WS", "/ws"),
]

# Even in DEMO_MODE these need a real admin token: they expose the filesystem,
# shells, raw data dumps or biometric data.
DANGEROUS_PREFIXES = (
    "/files",
    "/git",
    "/terminal",
    "/export",
    "/memory/export",
    "/testing/rollback",
    "/admin/face/embeddings",
    "/admin/voice",
    "/admin/daemons",
)

# Dependency names that mean "this route already authenticates".
_SELF_AUTH_DEPENDENCIES = {"require_admin", "require_auth", "get_current_user"}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# endpoint -> level, filled by classify_routes()
_ENDPOINT_LEVELS: Dict[object, str] = {}


# ---------------------------------------------------------------------------
# Classification (runs once at startup)
# ---------------------------------------------------------------------------

def _matches(rules, method: str, path: str) -> bool:
    for rule_method, pattern in rules:
        if rule_method not in ("*", method):
            continue
        if path == pattern or fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def _declares_own_auth(route) -> bool:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False

    def walk(dep) -> bool:
        for sub in dep.dependencies:
            if getattr(sub.call, "__name__", None) in _SELF_AUTH_DEPENDENCIES:
                return True
            if walk(sub):
                return True
        return False

    return walk(dependant)


def _in_admin_area(path: str) -> bool:
    return path == ADMIN_AREA or path.startswith(ADMIN_AREA + "/")


def level_for(method: str, path: str, route=None) -> str:
    if _matches(PUBLIC_ROUTES, method, path):
        return PUBLIC
    if _in_admin_area(path):
        if not _matches(ADMIN_AREA_USER_ROUTES, method, path):
            return ADMIN
        if route is not None and _declares_own_auth(route):
            return SELF
        return USER
    if _matches(SELF_ROUTES, method, path):
        return SELF
    if route is not None and _declares_own_auth(route):
        return SELF
    if _matches(USER_ROUTES, method, path):
        return USER
    return ADMIN


def iter_mounted_routes(app):
    """Yield (method, full_path, route, endpoint) for every mounted route.

    Methods are expanded (one tuple per method); websocket routes get "WS".
    Works with FastAPI's lazily-included routers.
    """
    try:
        from fastapi.routing import iter_route_contexts
        contexts = iter_route_contexts(app.routes)
    except ImportError:  # older FastAPI: app.routes is already flat
        contexts = app.routes

    for ctx in contexts:
        path = getattr(ctx, "path_format", None) or getattr(ctx, "path", None)
        endpoint = getattr(ctx, "endpoint", None)
        if not path or endpoint is None:
            continue  # Mounts (static files) have no endpoint
        original = getattr(ctx, "original_route", ctx)
        methods = getattr(ctx, "methods", None)
        if methods:
            for m in sorted(methods):
                yield m, path, original, endpoint
        else:
            yield "WS", path, original, endpoint


def classify_routes(app) -> Dict[Tuple[str, str], str]:
    """Assign a level to every mounted endpoint. Returns {(method, path): level}."""
    table = {}
    _ENDPOINT_LEVELS.clear()
    order = {PUBLIC: 0, USER: 1, SELF: 1, ADMIN: 2}
    for method, path, route, endpoint in iter_mounted_routes(app):
        level = level_for(method, path, route)
        table[(method, path)] = level
        # If one function is mounted twice, keep the stricter level.
        previous = _ENDPOINT_LEVELS.get(endpoint)
        if previous is None or order[level] > order[previous]:
            _ENDPOINT_LEVELS[endpoint] = level
    return table


# ---------------------------------------------------------------------------
# Request-time check
# ---------------------------------------------------------------------------

def _token_from(conn: HTTPConnection) -> Optional[str]:
    header = conn.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    if conn.scope.get("type") == "websocket":
        return conn.query_params.get("token") or None
    return None


def resolve_principal(conn: HTTPConnection):
    """Return (principal_or_None, user_id, via_localhost_bypass).

    Tokens are verified by auth.verify_access_token (one token format, plus
    the two legacy formats until they expire).
    """
    from auth import verify_access_token, localhost_bypass_user

    token = _token_from(conn)
    if token:
        principal = verify_access_token(token)
        if principal is not None:
            return principal, principal.user_id, False
    bypass = localhost_bypass_user(conn)
    if bypass:
        return None, bypass, True
    return None, None, False


def resolve_user(conn: HTTPConnection) -> Tuple[Optional[str], bool]:
    """Return (user_id, via_localhost_bypass)."""
    _principal, user_id, via_bypass = resolve_principal(conn)
    return user_id, via_bypass


def user_is_admin(user_id: str) -> bool:
    try:
        from database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def principal_is_admin(principal, user_id: str) -> bool:
    """Admin = users.is_admin in SQLite, capped by the token's role claim.

    A token whose roles leave out "admin" never gets admin access, even if
    the user was promoted after it was issued (log in again). Legacy tokens
    have no role claim, so for them (and the localhost bypass) SQLite decides.
    """
    if principal is not None and not principal.may_be_admin:
        return False
    return user_is_admin(user_id)


def _deny(conn: HTTPConnection, code: int, detail: str):
    if conn.scope.get("type") == "websocket":
        raise WebSocketException(code=1008, reason=detail)
    headers = {"WWW-Authenticate": "Bearer"} if code == status.HTTP_401_UNAUTHORIZED else None
    raise HTTPException(status_code=code, detail=detail, headers=headers)


def _is_dangerous(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in DANGEROUS_PREFIXES)


async def route_guard(conn: HTTPConnection):
    """App-wide dependency. See module docstring."""
    endpoint = conn.scope.get("endpoint")
    # Unknown endpoints (added after classify_routes ran) default to admin.
    level = _ENDPOINT_LEVELS.get(endpoint, ADMIN)
    if level == PUBLIC:
        return None

    method = conn.scope.get("method", "WS")
    path = conn.url.path

    if level == SELF:
        # The route checks auth itself. Only step in for DEMO_MODE: its
        # require_admin hands anonymous GETs a demo principal, which must
        # not reach data dumps like /admin/daemons/{id}/export.
        if config.DEMO_MODE and _is_dangerous(path) and resolve_user(conn)[0] is None:
            _deny(conn, status.HTTP_401_UNAUTHORIZED, "Authentication required")
        return None

    principal, user_id, _via_bypass = resolve_principal(conn)

    if user_id is None:
        if config.DEMO_MODE and not _is_dangerous(path):
            if method in SAFE_METHODS:
                conn.scope["cass_demo_anonymous"] = True
                return None
            # GraphQL queries are POSTs; mutations are blocked by
            # graphql_schema.DemoReadOnlyExtension instead.
            if method == "POST" and path.rstrip("/") == "/graphql":
                conn.scope["cass_demo_anonymous"] = True
                return None
            _deny(conn, status.HTTP_403_FORBIDDEN, "Demo mode is read-only. Log in to make changes.")
        _deny(conn, status.HTTP_401_UNAUTHORIZED, "Authentication required")

    if level == ADMIN and not principal_is_admin(principal, user_id):
        _deny(conn, status.HTTP_403_FORBIDDEN, "Admin access required")

    conn.scope["cass_user_id"] = user_id
    return None
