"""
Tests for auth.py - Authentication and authorization.

Tests cover:
- Password hashing and verification
- JWT token creation and decoding
- Token types (access vs refresh)
- Pydantic models
- Request helpers
- Authorization helpers
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_tokens,
    decode_token,
    is_localhost_request,
    require_ownership,
    TokenData,
    Token,
    UserAuth,
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    SECRET_KEY,
    ALGORITHM
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Password Hashing Tests
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_string(self):
        """hash_password should return a string."""
        hashed = hash_password("mysecretpassword")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_each_time(self):
        """Same password should produce different hashes (salting)."""
        hash1 = hash_password("password123")
        hash2 = hash_password("password123")
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        password = "correctpassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """verify_password should return False for wrong password."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_truncates_long_passwords(self):
        """Should handle passwords longer than bcrypt's 72 byte limit."""
        long_password = "a" * 100
        hashed = hash_password(long_password)
        # Should still work - truncation happens internally
        assert verify_password(long_password, hashed) is True

    def test_verify_truncated_passwords_match(self):
        """Passwords differing only after 72 bytes should match."""
        # bcrypt only considers first 72 bytes
        pass1 = "a" * 72 + "different"
        pass2 = "a" * 72 + "ending"
        hashed = hash_password(pass1)
        # Both should verify because truncation
        assert verify_password(pass2, hashed) is True


# ---------------------------------------------------------------------------
# JWT Token Tests
# ---------------------------------------------------------------------------

class TestJWTTokens:
    """Tests for JWT token functions."""

    def test_create_access_token(self):
        """create_access_token should return a JWT string."""
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0
        assert "." in token  # JWT has three parts

    def test_create_refresh_token(self):
        """create_refresh_token should return a JWT string."""
        token = create_refresh_token("user-456")
        assert isinstance(token, str)
        assert "." in token

    def test_create_tokens_returns_both(self):
        """create_tokens should return Token with both tokens."""
        tokens = create_tokens("user-789")
        assert isinstance(tokens, Token)
        assert tokens.access_token is not None
        assert tokens.refresh_token is not None
        assert tokens.token_type == "bearer"

    def test_decode_access_token(self):
        """decode_token should extract user_id from access token."""
        token = create_access_token("user-abc")
        data = decode_token(token)
        assert data is not None
        assert data.user_id == "user-abc"
        assert data.token_type == "access"

    def test_decode_refresh_token(self):
        """decode_token should identify refresh token type."""
        token = create_refresh_token("user-def")
        data = decode_token(token)
        assert data is not None
        assert data.user_id == "user-def"
        assert data.token_type == "refresh"

    def test_decode_invalid_token(self):
        """decode_token should return None for invalid token."""
        result = decode_token("invalid.jwt.token")
        assert result is None

    def test_decode_tampered_token(self):
        """decode_token should return None for tampered token."""
        token = create_access_token("user-123")
        # Tamper with the token
        parts = token.split(".")
        tampered = parts[0] + ".tampered." + parts[2]
        result = decode_token(tampered)
        assert result is None

    def test_access_token_different_from_refresh(self):
        """Access and refresh tokens should be different."""
        tokens = create_tokens("user-123")
        assert tokens.access_token != tokens.refresh_token


# ---------------------------------------------------------------------------
# Pydantic Models Tests
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Tests for Pydantic models."""

    def test_token_data_creation(self):
        """TokenData should store user_id and type."""
        data = TokenData(user_id="user-123", token_type="access")
        assert data.user_id == "user-123"
        assert data.token_type == "access"

    def test_token_data_default_type(self):
        """TokenData should default to 'access' type."""
        data = TokenData(user_id="user-123")
        assert data.token_type == "access"

    def test_token_model(self):
        """Token should store both tokens and type."""
        token = Token(
            access_token="access.jwt.here",
            refresh_token="refresh.jwt.here"
        )
        assert token.token_type == "bearer"

    def test_user_auth_model(self):
        """UserAuth should store auth credentials."""
        auth = UserAuth(
            email="test@example.com",
            password_hash="hashed_value",
            created_at="2025-01-15T00:00:00"
        )
        assert auth.email == "test@example.com"
        assert auth.last_login is None

    def test_register_request_validates_email(self):
        """RegisterRequest should validate email format."""
        req = RegisterRequest(
            email="valid@example.com",
            password="secret123",
            display_name="Test User"
        )
        assert req.email == "valid@example.com"

    def test_login_request(self):
        """LoginRequest should store credentials."""
        req = LoginRequest(
            email="user@example.com",
            password="password123"
        )
        assert req.email == "user@example.com"

    def test_refresh_request(self):
        """RefreshRequest should store refresh token."""
        req = RefreshRequest(refresh_token="some.refresh.token")
        assert req.refresh_token == "some.refresh.token"


# ---------------------------------------------------------------------------
# Request Helper Tests
# ---------------------------------------------------------------------------

class TestRequestHelpers:
    """Tests for request helper functions."""

    def test_is_localhost_127(self):
        """Should identify 127.0.0.1 as localhost."""
        request = Mock()
        request.client = Mock()
        request.client.host = "127.0.0.1"
        assert is_localhost_request(request) is True

    def test_is_localhost_ipv6(self):
        """Should identify ::1 as localhost."""
        request = Mock()
        request.client = Mock()
        request.client.host = "::1"
        assert is_localhost_request(request) is True

    def test_is_localhost_string(self):
        """Should identify 'localhost' as localhost."""
        request = Mock()
        request.client = Mock()
        request.client.host = "localhost"
        assert is_localhost_request(request) is True

    def test_is_not_localhost(self):
        """Should identify remote address as not localhost."""
        request = Mock()
        request.client = Mock()
        request.client.host = "192.168.1.100"
        assert is_localhost_request(request) is False

    def test_is_localhost_no_client(self):
        """Should handle missing client gracefully."""
        request = Mock()
        request.client = None
        assert is_localhost_request(request) is False


# ---------------------------------------------------------------------------
# Authorization Helper Tests
# ---------------------------------------------------------------------------

class TestAuthorizationHelpers:
    """Tests for authorization helper functions."""

    def test_require_ownership_passes(self):
        """Should not raise when user owns resource."""
        # Should complete without exception
        require_ownership("user-123", "user-123", "document")

    def test_require_ownership_fails(self):
        """Should raise 403 when user doesn't own resource."""
        with pytest.raises(HTTPException) as exc_info:
            require_ownership("user-123", "user-456", "document")

        assert exc_info.value.status_code == 403
        assert "document" in exc_info.value.detail

    def test_require_ownership_custom_resource_name(self):
        """Should include resource name in error message."""
        with pytest.raises(HTTPException) as exc_info:
            require_ownership("owner", "not-owner", "conversation")

        assert "conversation" in exc_info.value.detail


# ---------------------------------------------------------------------------
# AuthService Tests (Mocked)
# ---------------------------------------------------------------------------

class TestAuthServiceMocked:
    """Mocked tests for AuthService."""

    def test_auth_service_init(self):
        """AuthService should initialize with user_manager."""
        from auth import AuthService

        mock_user_manager = Mock()
        service = AuthService(mock_user_manager)
        assert service.user_manager == mock_user_manager

    def test_get_user_by_email_not_found(self):
        """get_user_by_email should return None when not found."""
        from auth import AuthService

        mock_user_manager = Mock()
        mock_user_manager.list_users.return_value = []

        service = AuthService(mock_user_manager)
        result = service.get_user_by_email("notfound@example.com")

        assert result is None

    def test_login_invalid_email(self):
        """login should raise 401 for unknown email."""
        from auth import AuthService

        mock_user_manager = Mock()
        mock_user_manager.list_users.return_value = []

        service = AuthService(mock_user_manager)

        with pytest.raises(HTTPException) as exc_info:
            service.login("unknown@example.com", "password")

        assert exc_info.value.status_code == 401

    def test_refresh_invalid_token(self):
        """refresh should raise 401 for invalid token."""
        from auth import AuthService

        mock_user_manager = Mock()
        service = AuthService(mock_user_manager)

        with pytest.raises(HTTPException) as exc_info:
            service.refresh("invalid.token.here")

        assert exc_info.value.status_code == 401

    def test_refresh_wrong_token_type(self):
        """refresh should raise 401 when given access token."""
        from auth import AuthService

        mock_user_manager = Mock()
        service = AuthService(mock_user_manager)

        # Create an access token (not refresh)
        access_token = create_access_token("user-123")

        with pytest.raises(HTTPException) as exc_info:
            service.refresh(access_token)

        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Token Expiration Tests
# ---------------------------------------------------------------------------

class TestTokenExpiration:
    """Tests for token expiration behavior."""

    def test_expired_token_rejected(self):
        """Expired tokens should not decode."""
        from jose import jwt

        # Create a token that's already expired
        expire = datetime.utcnow() - timedelta(hours=1)
        to_encode = {
            "sub": "user-123",
            "type": "access",
            "exp": expire
        }
        expired_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(expired_token)
        assert result is None

    def test_token_with_no_sub_rejected(self):
        """Tokens without 'sub' claim should be rejected."""
        from jose import jwt

        to_encode = {
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        result = decode_token(token)
        assert result is None
