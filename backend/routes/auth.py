"""
Cass Vessel - Authentication Routes
Endpoints for user registration, login, and token refresh.
"""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from auth import (
    AuthService,
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    Token,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Auth endpoints use IP-based rate limiting (no auth yet)
limiter = Limiter(key_func=get_remote_address)

# Will be initialized by main_sdk.py
_auth_service: AuthService = None


def init_auth_routes(auth_service: AuthService):
    """Initialize routes with auth service instance"""
    global _auth_service
    _auth_service = auth_service


@router.post("/register", response_model=dict)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest):
    """
    Register a new user account.

    Returns user_id and tokens on success.
    Rate limited to 5 requests per minute per IP.
    """
    user_id, tokens = _auth_service.register(
        email=body.email,
        password=body.password,
        display_name=body.display_name
    )
    return {
        "user_id": user_id,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer"
    }


@router.post("/login", response_model=dict)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """
    Authenticate and get tokens.

    Returns user_id and tokens on success.
    Rate limited to 10 requests per minute per IP.
    """
    user_id, tokens = _auth_service.login(
        email=body.email,
        password=body.password
    )
    return {
        "user_id": user_id,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=dict)
@limiter.limit("30/minute")
async def refresh(request: Request, body: RefreshRequest):
    """
    Refresh access token using refresh token.

    Returns new access and refresh tokens.
    Rate limited to 30 requests per minute per IP.
    """
    tokens = _auth_service.refresh(body.refresh_token)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer"
    }


@router.get("/me")
async def get_current_user_info(user_id: str = Depends(get_current_user)):
    """
    Get current authenticated user info.

    Requires valid access token.
    """
    profile = _auth_service.user_manager.load_profile(user_id)
    if not profile:
        return {"error": "User not found"}

    auth = _auth_service.get_user_auth(user_id)

    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "email": auth.email if auth else None,
        "relationship": profile.relationship,
        "created_at": profile.created_at
    }
