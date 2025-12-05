"""
Cass Vessel - Authentication Routes
Endpoints for user registration, login, and token refresh.
"""
from fastapi import APIRouter, Depends
from auth import (
    AuthService,
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    Token,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Will be initialized by main_sdk.py
_auth_service: AuthService = None


def init_auth_routes(auth_service: AuthService):
    """Initialize routes with auth service instance"""
    global _auth_service
    _auth_service = auth_service


@router.post("/register", response_model=dict)
async def register(request: RegisterRequest):
    """
    Register a new user account.

    Returns user_id and tokens on success.
    """
    user_id, tokens = _auth_service.register(
        email=request.email,
        password=request.password,
        display_name=request.display_name
    )
    return {
        "user_id": user_id,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer"
    }


@router.post("/login", response_model=dict)
async def login(request: LoginRequest):
    """
    Authenticate and get tokens.

    Returns user_id and tokens on success.
    """
    user_id, tokens = _auth_service.login(
        email=request.email,
        password=request.password
    )
    return {
        "user_id": user_id,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=dict)
async def refresh(request: RefreshRequest):
    """
    Refresh access token using refresh token.

    Returns new access and refresh tokens.
    """
    tokens = _auth_service.refresh(request.refresh_token)
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
