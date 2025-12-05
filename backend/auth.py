"""
Cass Vessel - Authentication Module
JWT-based authentication with password hashing.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel, EmailStr
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration - should come from environment
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND")
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


# === JWT Utilities ===

def create_access_token(user_id: str) -> str:
    """Create an access token for a user"""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "type": "access",
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a refresh token for a user"""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_tokens(user_id: str) -> Token:
    """Create both access and refresh tokens"""
    return Token(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id)
    )


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if user_id is None:
            return None
        return TokenData(user_id=user_id, token_type=token_type)
    except JWTError:
        return None


# === Request Helpers ===

def is_localhost_request(request: Request) -> bool:
    """Check if request originates from localhost"""
    client_host = request.client.host if request.client else None
    # Check for localhost addresses
    localhost_addresses = {"127.0.0.1", "::1", "localhost"}
    return client_host in localhost_addresses


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

    token_data = decode_token(token)
    if token_data is None:
        return None

    if token_data.token_type != "access":
        return None

    return token_data.user_id


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

    if user_id is not None:
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


# === Auth Service ===

class AuthService:
    """
    Authentication service that integrates with UserManager.
    Handles registration, login, and token refresh.
    """

    def __init__(self, user_manager):
        self.user_manager = user_manager
        self._auth_cache = {}  # user_id -> UserAuth (in-memory cache)

    def _get_auth_path(self, user_id: str):
        """Get path to user's auth.json file"""
        return self.user_manager._get_user_dir(user_id) / "auth.json"

    def _load_auth(self, user_id: str) -> Optional[UserAuth]:
        """Load auth credentials for a user"""
        import json
        path = self._get_auth_path(user_id)
        if not path.exists():
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return UserAuth(**data)
        except Exception:
            return None

    def _save_auth(self, user_id: str, auth: UserAuth):
        """Save auth credentials for a user"""
        import json
        path = self._get_auth_path(user_id)
        with open(path, 'w') as f:
            json.dump(auth.model_dump(), f, indent=2)

    def get_user_by_email(self, email: str) -> Optional[str]:
        """Find user_id by email address"""
        # Check all users for matching email
        for user_info in self.user_manager.list_users():
            user_id = user_info["user_id"]
            auth = self._load_auth(user_id)
            if auth and auth.email.lower() == email.lower():
                return user_id
        return None

    def register(
        self,
        email: str,
        password: str,
        display_name: str
    ) -> tuple[str, Token]:
        """
        Register a new user.
        Returns (user_id, tokens) on success.
        Raises HTTPException on failure.
        """
        # Check if email already exists
        if self.get_user_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user profile
        profile = self.user_manager.create_user(
            display_name=display_name,
            relationship="user"
        )

        # Create auth record
        now = datetime.now().isoformat()
        auth = UserAuth(
            email=email.lower(),
            password_hash=hash_password(password),
            created_at=now,
            last_login=now
        )
        self._save_auth(profile.user_id, auth)

        # Generate tokens
        tokens = create_tokens(profile.user_id)

        return profile.user_id, tokens

    def login(self, email: str, password: str) -> tuple[str, Token]:
        """
        Authenticate a user and return tokens.
        Raises HTTPException on failure.
        """
        # Find user by email
        user_id = self.get_user_by_email(email)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Verify password
        auth = self._load_auth(user_id)
        if not auth or not verify_password(password, auth.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Update last login
        auth.last_login = datetime.now().isoformat()
        self._save_auth(user_id, auth)

        # Generate tokens
        tokens = create_tokens(user_id)

        return user_id, tokens

    def refresh(self, refresh_token: str) -> Token:
        """
        Refresh access token using refresh token.
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

        # Verify user still exists
        profile = self.user_manager.load_profile(token_data.user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Generate new tokens
        return create_tokens(token_data.user_id)

    def get_user_auth(self, user_id: str) -> Optional[UserAuth]:
        """Get auth info for a user (without password hash)"""
        return self._load_auth(user_id)


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
