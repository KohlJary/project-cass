"""
Admin API - Authentication & User Approval Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel
import os
import jwt
import secrets

from config import DEMO_MODE

router = APIRouter(tags=["admin-auth"])

# JWT Configuration
JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer(auto_error=False)

# Reference to users manager - set by init function
_users = None


def init_users(users_manager):
    """Initialize users manager reference."""
    global _users
    _users = users_manager


# ============== Pydantic Models ==============

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str
    display_name: str
    is_admin: bool
    expires_at: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    registration_reason: Optional[str] = None


class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None


class BootstrapRequest(BaseModel):
    username: str
    password: str


class RejectRequest(BaseModel):
    reason: str


# ============== Auth Helpers ==============

def create_token(user_id: str, display_name: str, is_admin: bool = False) -> tuple[str, datetime]:
    """Create a JWT token for an admin user"""
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "display_name": display_name,
        "is_admin": is_admin,
        "exp": expires,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires


def verify_token(token: str) -> Optional[Dict]:
    """Verify a JWT token and return payload if valid"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """Dependency that requires valid admin authentication.

    In demo mode, returns a demo user without requiring authentication.
    """
    # Demo mode bypasses authentication
    if DEMO_MODE:
        return {
            "user_id": "demo",
            "display_name": "Demo User",
            "is_admin": True,
            "demo_mode": True
        }

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Verify user still has admin access
    if _users:
        profile = _users.load_profile(payload["user_id"])
        if not profile or not profile.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin access revoked"
            )

    return payload


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """Dependency that requires valid authentication (any user, not just admin).

    In demo mode, returns a demo user without requiring authentication.
    """
    # Demo mode bypasses authentication
    if DEMO_MODE:
        return {
            "user_id": "demo",
            "display_name": "Demo User",
            "is_admin": True,
            "demo_mode": True
        }

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload


# ============== Auth Endpoints ==============

@router.post("/auth/bootstrap")
async def bootstrap_admin(request: BootstrapRequest):
    """One-time bootstrap: set up first admin user.

    If no admin users exist, promotes the specified user to admin, approves them,
    and sets their password. Otherwise, only sets password for existing passwordless admins.
    """
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    profile = _users.get_user_by_name(request.username)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if any admin users exist
    from database import get_db
    with get_db() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]

    # If no admins exist, promote this user to admin
    if admin_count == 0:
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET is_admin = 1, status = 'approved' WHERE id = ?",
                (profile.user_id,)
            )
        # Reload profile
        profile = _users.get_user_by_name(request.username)
    elif not profile.is_admin:
        raise HTTPException(status_code=403, detail="User is not an admin")
    elif profile.password_hash:
        raise HTTPException(status_code=400, detail="User already has a password set")

    # Set the password
    try:
        result = _users.set_admin_password(profile.user_id, request.password)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to set password (returned False)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set password: {str(e)}")

    return {"status": "ok", "message": f"Password set for {request.username} (admin: {profile.is_admin})"}


@router.post("/auth/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest):
    """Login to admin dashboard.

    Users must be approved (status='approved') to log in.
    Pending or rejected users will receive appropriate error messages.
    """
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    # First check if user exists and verify password
    profile = _users.get_user_by_name(request.username)
    if not profile:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not profile.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _users.verify_password(request.password, profile.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check account status
    if profile.status == 'pending':
        raise HTTPException(
            status_code=403,
            detail="Account pending approval. Please wait for an administrator to approve your registration."
        )
    if profile.status == 'rejected':
        reason = profile.rejection_reason or "No reason provided"
        raise HTTPException(
            status_code=403,
            detail=f"Account rejected: {reason}"
        )

    token, expires = create_token(profile.user_id, profile.display_name, profile.is_admin)

    return LoginResponse(
        token=token,
        user_id=profile.user_id,
        display_name=profile.display_name,
        is_admin=profile.is_admin,
        expires_at=expires.isoformat()
    )


@router.get("/auth/verify")
async def verify_admin(admin: Dict = Depends(require_admin)):
    """Verify current token is valid and return user info including role"""
    is_admin = False
    if not admin.get("demo_mode") and _users:
        profile = _users.load_profile(admin["user_id"])
        if profile:
            is_admin = profile.is_admin

    return {
        "valid": True,
        "user_id": admin["user_id"],
        "display_name": admin["display_name"],
        "is_admin": is_admin or admin.get("demo_mode", False),
        "demo_mode": admin.get("demo_mode", False)
    }


@router.get("/auth/status")
async def auth_status():
    """Get authentication status (public endpoint).

    Returns whether demo mode is enabled so the frontend can skip login.
    """
    return {
        "demo_mode": DEMO_MODE
    }


@router.post("/auth/register", response_model=RegisterResponse)
async def register_user(request: RegisterRequest):
    """Register a new user account (public endpoint).

    New users start with status='pending' and must be approved by an admin
    before they can log in.
    """
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    # Check if username already exists
    existing = _users.get_user_by_name(request.username)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Username already taken"
        )

    # Validate password
    if len(request.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters"
        )

    # Create user with pending status
    import uuid
    from datetime import datetime

    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    # Insert user into database
    from database import get_db
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (id, display_name, status, email, registration_reason, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
        """, (user_id, request.username, request.email, request.registration_reason, now, now))

    # Set the password
    _users.set_admin_password(user_id, request.password)

    return RegisterResponse(
        success=True,
        message="Registration submitted. Please wait for admin approval.",
        user_id=user_id
    )


@router.post("/auth/set-password")
async def set_admin_password(
    user_id: str,
    password: str,
    admin: Dict = Depends(require_admin)
):
    """Set password for an admin user (requires existing admin)"""
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    success = _users.set_admin_password(user_id, password)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True}


# ============== User Approval Endpoints ==============

@router.get("/users/pending")
async def get_pending_users(admin: Dict = Depends(require_admin)):
    """Get users awaiting approval (admin only)."""
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    pending = _users.get_pending_users()
    return {
        "users": [
            {
                "id": u.user_id,
                "display_name": u.display_name,
                "email": u.email,
                "registration_reason": u.registration_reason,
                "created_at": u.created_at
            }
            for u in pending
        ]
    }


@router.post("/users/{user_id}/approve")
async def approve_user(user_id: str, admin: Dict = Depends(require_admin)):
    """Approve a pending user (admin only)."""
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    profile = _users.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if profile.status != 'pending':
        raise HTTPException(
            status_code=400,
            detail=f"User is not pending approval (status: {profile.status})"
        )

    success = _users.set_user_status(user_id, 'approved')
    if not success:
        raise HTTPException(status_code=500, detail="Failed to approve user")

    # Send approval email if email is configured and user has an email
    email_sent = False
    if profile.email:
        from email_service import send_approval_email
        email_sent = send_approval_email(profile.email, profile.display_name)

    return {
        "success": True,
        "message": f"User {profile.display_name} approved",
        "email_sent": email_sent
    }


@router.post("/users/{user_id}/reject")
async def reject_user(
    user_id: str,
    request: RejectRequest,
    admin: Dict = Depends(require_admin)
):
    """Reject a pending user with a reason (admin only)."""
    if not _users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    profile = _users.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    if profile.status != 'pending':
        raise HTTPException(
            status_code=400,
            detail=f"User is not pending approval (status: {profile.status})"
        )

    success = _users.set_user_status(user_id, 'rejected', request.reason)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reject user")

    # Send rejection email if email is configured and user has an email
    email_sent = False
    if profile.email:
        from email_service import send_rejection_email
        email_sent = send_rejection_email(profile.email, profile.display_name, request.reason)

    return {
        "success": True,
        "message": f"User {profile.display_name} rejected",
        "email_sent": email_sent
    }
