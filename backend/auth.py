"""
Cass Vessel - Authentication Module
JWT-based authentication with password hashing.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from pydantic import BaseModel, EmailStr
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration - should come from environment.
# If JWT_SECRET_KEY is unset we must NOT fall back to a constant (anyone could
# mint tokens with it); use a random secret persisted in DATA_DIR instead.
from secret_store import get_or_create_secret
SECRET_KEY = get_or_create_secret("user_jwt_secret", "JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

# Bearer token extractor
security = HTTPBearer(auto_error=False)


# === Pydantic Models ===

class TokenData(BaseModel):
    """Data encoded in JWT"""
    user_id: str
    token_type: str = "access"  # "access" or "refresh"
    roles: Optional[list] = None  # None for legacy tokens without a role claim


class Token(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserAuth(BaseModel):
    """User authentication credentials stored in profile"""
    email: str
    password_hash: str
    created_at: str
    last_login: Optional[str] = None


class RegisterRequest(BaseModel):
    """Registration request"""
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str


# === Password Utilities ===

def hash_password(password: str) -> str:
    """Hash a password for storage"""
    # Truncate to 72 bytes (bcrypt limit) to handle long passwords
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    password_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


# === Tokens ===
#
# One token format (issue #61). Every token is an HS256 JWT signed with
# SECRET_KEY and carries:
#     sub, user_id  - the SQLite users.id (both names, so code that read either
#                     of the two old formats keeps working)
#     type          - "access" or "refresh"
#     roles         - ["user"] or ["user", "admin"], from users.is_admin at issue
#     display_name  - optional, informational
#     ver           - TOKEN_VERSION
#     iat, exp
# Tokens are verified in one place: verify_token_claims() / verify_access_token().
#
# Transition: two older formats are still accepted until they expire.
#   - "user-v1": the old mobile/TUI token (same secret; sub/type/exp, no roles).
#   - "admin-v1": the old admin-dashboard token (signed with the admin secret,
#     DATA_DIR/.secrets/admin_jwt_secret or ADMIN_JWT_SECRET; user_id,
#     display_name, is_admin, exp, iat; lived 24 hours).
# Nothing issues those formats any more. Legacy tokens carry no usable role
# claim, so for them SQLite alone decides admin access (as before).

import jwt as pyjwt
from dataclasses import dataclass, field

TOKEN_VERSION = 2
ROLE_USER = "user"
ROLE_ADMIN = "admin"
# The admin dashboard has no refresh flow, so its logins get the lifetime its
# old tokens had (24h) instead of the mobile app's 30 minutes.
DASHBOARD_ACCESS_EXPIRE_HOURS = int(os.getenv("JWT_DASHBOARD_EXPIRE_HOURS", "24"))
_LEEWAY_SECONDS = 30

_legacy_admin_secret: Optional[str] = None


def _admin_legacy_secret() -> str:
    """Secret the old admin-dashboard tokens were signed with (verify only)."""
    global _legacy_admin_secret
    if _legacy_admin_secret is None:
        _legacy_admin_secret = get_or_create_secret("admin_jwt_secret", "ADMIN_JWT_SECRET")
    return _legacy_admin_secret


def roles_for_user(user_id: str) -> list:
    """Roles a token issued now should carry, from users.is_admin."""
    try:
        from database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and row[0]:
            return [ROLE_USER, ROLE_ADMIN]
    except Exception:
        pass
    return [ROLE_USER]


def _issue(user_id: str, token_type: str, lifetime: timedelta,
           roles: Optional[list] = None, display_name: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "type": token_type,
        "roles": list(roles) if roles is not None else roles_for_user(user_id),
        "ver": TOKEN_VERSION,
        "iat": now,
        "exp": now + lifetime,
    }
    if display_name:
        payload["display_name"] = display_name
    return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str, roles: Optional[list] = None,
                        display_name: Optional[str] = None,
                        expires_delta: Optional[timedelta] = None) -> str:
    """Create an access token. Roles default to what SQLite says now."""
    lifetime = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return _issue(user_id, "access", lifetime, roles, display_name)


def create_refresh_token(user_id: str, roles: Optional[list] = None) -> str:
    """Create a refresh token for a user"""
    return _issue(user_id, "refresh", timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), roles)


def create_tokens(user_id: str, roles: Optional[list] = None) -> Token:
    """Create both access and refresh tokens"""
    if roles is None:
        roles = roles_for_user(user_id)
    return Token(
        access_token=create_access_token(user_id, roles=roles),
        refresh_token=create_refresh_token(user_id, roles=roles)
    )


def create_dashboard_token(user_id: str, display_name: str,
                           roles: Optional[list] = None) -> tuple:
    """Access token for the admin dashboard login: (token, expires_at)."""
    lifetime = timedelta(hours=DASHBOARD_ACCESS_EXPIRE_HOURS)
    expires = datetime.now(timezone.utc) + lifetime
    token = create_access_token(user_id, roles=roles, display_name=display_name,
                                expires_delta=lifetime)
    return token, expires.replace(tzinfo=None)


@dataclass
class Principal:
    """Who a verified token says the caller is."""
    user_id: str
    token_type: str = "access"
    # None for legacy tokens: they carry no role claim, so SQLite decides.
    roles: Optional[tuple] = None
    format: str = "v2"          # "v2", "user-v1" or "admin-v1"
    claims: dict = field(default_factory=dict)

    @property
    def may_be_admin(self) -> bool:
        """The token does not rule out admin access (SQLite must still agree)."""
        return self.roles is None or ROLE_ADMIN in self.roles


def _decode(token: str, secret: str) -> Optional[dict]:
    try:
        return pyjwt.decode(
            token, secret, algorithms=[ALGORITHM],
            options={"require": ["exp"]}, leeway=_LEEWAY_SECONDS,
        )
    except pyjwt.PyJWTError:
        return None
    except Exception:
        return None


def verify_token_claims(token: str) -> Optional[Principal]:
    """Verify a token of any accepted format. The one place tokens are checked."""
    if not token or not isinstance(token, str):
        return None
    payload = _decode(token, SECRET_KEY)
    if payload is not None:
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id or not isinstance(user_id, str):
            return None
        token_type = payload.get("type", "access")
        if "ver" in payload or "roles" in payload:
            roles = payload.get("roles")
            if not isinstance(roles, list):
                return None
            return Principal(user_id, token_type, tuple(str(r) for r in roles), "v2", payload)
        return Principal(user_id, token_type, None, "user-v1", payload)

    # Legacy admin-dashboard token (accepted until it expires; 24h lifetime).
    payload = _decode(token, _admin_legacy_secret())
    if payload is not None and isinstance(payload.get("user_id"), str) and payload["user_id"]:
        return Principal(payload["user_id"], "access", None, "admin-v1", payload)
    return None


def verify_access_token(token: str) -> Optional[Principal]:
    """A verified ACCESS token (refresh tokens are refused)."""
    principal = verify_token_claims(token)
    if principal is None or principal.token_type != "access":
        return None
    return principal


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token (any accepted format)."""
    principal = verify_token_claims(token)
    if principal is None:
        return None
    return TokenData(
        user_id=principal.user_id,
        token_type=principal.token_type,
        roles=list(principal.roles) if principal.roles is not None else None,
    )


# === Request Helpers ===

# Headers that mean "this connection was forwarded by a proxy on this box".
# A proxied request arrives from 127.0.0.1 but did not originate locally, so it
# must never get the localhost bypass. X-Cass-Relayed is set by relay_client.py
# on every request it proxies from the mobile relay; the others cover common
# reverse proxies / tunnels (nginx, cloudflared, Caddy).
PROXY_HEADERS = (
    "x-cass-relayed",
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
)


def is_localhost_request(request) -> bool:
    """Check if a request (HTTP or WebSocket) genuinely originates from localhost."""
    client_host = request.client.host if request.client else None
    # Check for localhost addresses
    localhost_addresses = {"127.0.0.1", "::1", "localhost"}
    if client_host not in localhost_addresses:
        return False
    headers = getattr(request, "headers", None)
    try:
        if any(h in headers for h in PROXY_HEADERS):
            return False
        # A browser on this machine visiting some other website can still send
        # requests to localhost:8000. Browsers always attach Origin to those,
        # so only treat a request as local if its Origin (if any) is local too.
        origin = headers.get("origin") if headers is not None else None
    except TypeError:
        return True  # headers is not a mapping (unit-test mocks)
    if origin:
        from urllib.parse import urlparse
        if urlparse(origin).hostname not in localhost_addresses:
            return False
    return True


def localhost_bypass_user(request) -> Optional[str]:
    """User id granted by the localhost bypass, or None if it does not apply."""
    allow_localhost = os.getenv("ALLOW_LOCALHOST_BYPASS", "true").lower() == "true"
    if allow_localhost and is_localhost_request(request):
        return os.getenv("DEFAULT_LOCALHOST_USER_ID") or None
    return None


def user_id_from_any_token(token: str) -> Optional[str]:
    """User id from a valid access token of any accepted format, else None.

    Kept for callers written when there were two token systems; it now goes
    through verify_access_token like everything else.
    """
    principal = verify_access_token(token)
    return principal.user_id if principal else None


def get_token_from_request(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """Extract bearer token from request if present"""
    if credentials is None:
        return None
    return credentials.credentials


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request)
) -> Optional[str]:
    """
    Get current user from JWT token.
    Returns None if no valid token (allows localhost bypass).
    """
    if token is None:
        return None

    return user_id_from_any_token(token)


async def get_current_user(
    request: Request,
    user_id: Optional[str] = Depends(get_current_user_optional)
) -> str:
    """
    Get current user, requiring authentication.
    Raises 401 if not authenticated (unless localhost bypass is enabled).
    """
    # Check for localhost bypass
    allow_localhost = os.getenv("ALLOW_LOCALHOST_BYPASS", "true").lower() == "true"

    # Guard against being called directly (not via Depends): the default is
    # then the Depends marker itself, which used to be returned as the "user".
    if user_id is not None and isinstance(user_id, str):
        return user_id

    if allow_localhost and is_localhost_request(request):
        # Return a default user ID for localhost requests
        # This allows TUI to work without auth during transition
        default_user = os.getenv("DEFAULT_LOCALHOST_USER_ID")
        if default_user:
            return default_user
        # If no default set, still require auth
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No DEFAULT_LOCALHOST_USER_ID configured for localhost bypass",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# === Credential store ===
#
# One store: the SQLite users table (email, password_hash, status, is_admin).
# The mobile app's per-user DATA_DIR/users/<id>/auth.json files were the second
# store; scripts/migrate_auth_json.py copies them into SQLite. Until Kohl has
# run it (and decided to drop the fallback), login still READS auth.json when
# SQLite has no match. Nothing writes auth.json any more.
#
# Where the two stores disagreed, the migration keeps SQLite's value and puts
# the auth.json one in users.legacy_email / users.legacy_password_hash, so
# every password and email that worked before still works.

def check_password(plain_password: str, password_hash: Optional[str]) -> bool:
    """Check a password against either hash format the stores used."""
    if not password_hash or plain_password is None:
        return False
    try:
        if password_hash.startswith("$2"):
            return verify_password(plain_password, password_hash)
        from users import UserManager
        return UserManager.verify_password(plain_password, password_hash)
    except Exception:
        return False


def _users_query(sql_with_legacy: str, sql_without_legacy: str, params: tuple) -> list:
    """Run a users query; if the v62 legacy_* columns are missing, run the plain one.

    A database that has not been migrated yet must not lock anyone out.
    """
    from database import get_db
    try:
        with get_db() as conn:
            try:
                return [dict(r) for r in conn.execute(sql_with_legacy, params).fetchall()]
            except Exception as e:
                if "legacy_" not in str(e):
                    raise
                plain_params = params[:sql_without_legacy.count("?")]
                return [dict(r) for r in conn.execute(sql_without_legacy, plain_params).fetchall()]
    except Exception:
        return []


def _candidate_rows(identifier: str) -> list:
    """users rows an identifier (email or display name) could mean."""
    ident = (identifier or "").strip()
    if not ident:
        return []
    cols = "id, display_name, password_hash, status, rejection_reason, is_admin"
    return _users_query(
        f"SELECT {cols}, legacy_password_hash FROM users "
        "WHERE LOWER(display_name) = LOWER(?) OR LOWER(email) = LOWER(?) "
        "OR LOWER(legacy_email) = LOWER(?) ORDER BY created_at",
        f"SELECT {cols} FROM users "
        "WHERE LOWER(display_name) = LOWER(?) OR LOWER(email) = LOWER(?) ORDER BY created_at",
        (ident, ident, ident),
    )


def find_user_id_by_email(email: str) -> Optional[str]:
    """users.id whose email (or migrated legacy email) matches."""
    rows = _users_query(
        "SELECT id FROM users WHERE LOWER(email) = LOWER(?) "
        "OR LOWER(legacy_email) = LOWER(?) ORDER BY created_at LIMIT 1",
        "SELECT id FROM users WHERE LOWER(email) = LOWER(?) ORDER BY created_at LIMIT 1",
        (email, email),
    )
    return rows[0]["id"] if rows else None


def require_approved_status(account_status: Optional[str], rejection_reason: Optional[str] = None):
    """Refuse pending/rejected accounts (same messages on both login paths)."""
    account_status = account_status or "approved"
    if account_status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval. Please wait for an administrator to approve your registration."
        )
    if account_status == "rejected":
        reason = rejection_reason or "No reason provided"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account rejected: {reason}"
        )


def authenticate(identifier: str, password: str, user_manager=None) -> str:
    """The one credential check behind both login endpoints.

    `identifier` is an email or a display name. Returns the user id, or raises
    401 (bad credentials) / 403 (pending or rejected). Falls back to reading
    the legacy auth.json store when SQLite has no matching credential.
    """
    for row in _candidate_rows(identifier):
        if check_password(password, row.get("password_hash")) or \
                check_password(password, row.get("legacy_password_hash")):
            require_approved_status(row.get("status"), row.get("rejection_reason"))
            return row["id"]

    if user_manager is not None and "@" in (identifier or ""):
        user_id = _legacy_auth_json_login(user_manager, identifier, password)
        if user_id:
            profile = user_manager.load_profile(user_id)
            require_approved_status(getattr(profile, "status", None),
                                    getattr(profile, "rejection_reason", None))
            return user_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )


def _legacy_auth_files(user_manager):
    """(user_id, path) for every auth.json, without creating directories."""
    storage = getattr(user_manager, "storage_dir", None)
    try:
        from pathlib import Path
        storage = Path(storage)
        if not storage.is_dir():
            return []
        return [(p.parent.name, p) for p in sorted(storage.glob("*/auth.json"))]
    except Exception:
        return []


def _load_legacy_auth(path) -> Optional[UserAuth]:
    import json
    try:
        with open(path, "r") as f:
            return UserAuth(**json.load(f))
    except Exception:
        return None


def _legacy_auth_json_login(user_manager, email: str, password: str) -> Optional[str]:
    """Read-only fallback to the old auth.json store (transition only)."""
    for user_id, path in _legacy_auth_files(user_manager):
        auth = _load_legacy_auth(path)
        if auth and auth.email.lower() == email.lower() and check_password(password, auth.password_hash):
            import logging
            logging.getLogger(__name__).warning(
                "Login for %s used the legacy auth.json store; run "
                "scripts/migrate_auth_json.py to move it into SQLite.", user_id)
            return user_id
    return None


# === Auth Service ===

class AuthService:
    """
    Registration, login and token refresh for /auth/* (mobile app, TUI).
    Credentials live in SQLite; see "Credential store" above.
    """

    def __init__(self, user_manager):
        self.user_manager = user_manager

    def get_user_by_email(self, email: str) -> Optional[str]:
        """Find user_id by email address (SQLite, then the legacy auth.json)."""
        user_id = find_user_id_by_email(email)
        if user_id:
            return user_id
        for legacy_id, path in _legacy_auth_files(self.user_manager):
            auth = _load_legacy_auth(path)
            if auth and auth.email.lower() == email.lower():
                return legacy_id
        return None

    def register(
        self,
        email: str,
        password: str,
        display_name: str
    ) -> str:
        """
        Register a new user as PENDING (same approval flow as
        /admin/auth/register). No tokens are issued: the user can log in once
        an admin approves them (POST /admin/users/{id}/approve).
        Returns the new user_id. Raises HTTPException on failure.
        """
        if self.get_user_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        profile = self.user_manager.create_user(
            display_name=display_name,
            relationship="user",
            status="pending",
        )

        from database import get_db
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET email = ?, password_hash = ?, updated_at = ? WHERE id = ?",
                (email.lower(), hash_password(password), datetime.now().isoformat(),
                 profile.user_id),
            )

        return profile.user_id

    def login(self, email: str, password: str) -> tuple[str, Token]:
        """
        Authenticate a user and return tokens.
        Raises HTTPException on failure.
        """
        try:
            user_id = authenticate(email, password, self.user_manager)
        except HTTPException as e:
            if e.status_code == status.HTTP_401_UNAUTHORIZED:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            raise
        return user_id, create_tokens(user_id)

    def refresh(self, refresh_token: str) -> Token:
        """
        Refresh access token using refresh token (new or legacy format).
        Raises HTTPException on failure.
        """
        token_data = decode_token(refresh_token)

        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        if token_data.token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        profile = self.user_manager.load_profile(token_data.user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        require_approved_status(getattr(profile, "status", None),
                                getattr(profile, "rejection_reason", None))

        # Roles come from SQLite now, not from the old token.
        return create_tokens(token_data.user_id)

    def get_user_email(self, user_id: str) -> Optional[str]:
        """The user's login email (SQLite, then the legacy auth.json)."""
        rows = _users_query(
            "SELECT email, legacy_email FROM users WHERE id = ?",
            "SELECT email FROM users WHERE id = ?",
            (user_id,),
        )
        if rows:
            email = rows[0].get("email") or rows[0].get("legacy_email")
            if email:
                return email
        auth = self.get_user_auth(user_id)
        return auth.email if auth else None

    def get_user_auth(self, user_id: str) -> Optional[UserAuth]:
        """Legacy auth.json record for a user, if one exists (read-only)."""
        for legacy_id, path in _legacy_auth_files(self.user_manager):
            if legacy_id == user_id:
                return _load_legacy_auth(path)
        return None

    # Kept for older callers.
    def _require_approved(self, user_id: str):
        profile = self.user_manager.load_profile(user_id)
        require_approved_status(getattr(profile, "status", None),
                                getattr(profile, "rejection_reason", None))


# === Authorization Helpers ===

def require_ownership(resource_user_id: str, current_user_id: str, resource_name: str = "resource"):
    """
    Verify that the current user owns the resource.
    Raises 403 Forbidden if not.
    """
    if resource_user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access this {resource_name}"
        )


def check_conversation_ownership(
    conversation_manager,
    conversation_id: str,
    current_user_id: str
) -> bool:
    """
    Check if a conversation belongs to the current user.
    Returns True if owned, raises 403 if not.
    """
    conversation = conversation_manager.load_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Get user_id from conversation metadata
    conv_user_id = conversation.get("user_id")
    if conv_user_id and conv_user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation"
        )

    return True
