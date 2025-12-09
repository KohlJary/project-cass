#!/usr/bin/env python3
"""
Daedalus Authentication Manager

Manages authentication tokens for Daedalus (the Claude Code instance).
Stores credentials securely in the data directory (gitignored).

Usage:
    python scripts/daedalus_auth.py setup     # First-time setup (set password)
    python scripts/daedalus_auth.py token     # Get/refresh auth token
    python scripts/daedalus_auth.py info      # Show Daedalus user info
"""

import sys
import os
import json
import secrets
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from users import UserManager
from config import DATA_DIR

DAEDALUS_USER_ID = "7fe31ade-e3d2-42b7-a128-e0e3a6b46fa1"
CREDENTIALS_FILE = DATA_DIR / "daedalus_credentials.json"

# JWT config (must match admin_api.py)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def load_credentials():
    """Load Daedalus credentials from file"""
    if CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    return {}


def save_credentials(creds: dict):
    """Save Daedalus credentials to file"""
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(creds, f, indent=2)


def get_jwt_secret():
    """Get the JWT secret (must match what the server uses)"""
    # Check if server set a persistent secret
    secret = os.environ.get("ADMIN_JWT_SECRET")
    if secret:
        return secret

    # Check if we have a saved secret
    creds = load_credentials()
    if "jwt_secret" in creds:
        return creds["jwt_secret"]

    # Generate and save a new one
    secret = secrets.token_hex(32)
    creds["jwt_secret"] = secret
    save_credentials(creds)
    print(f"Generated new JWT secret. Set this in your environment:")
    print(f"  export ADMIN_JWT_SECRET={secret}")
    return secret


def create_token(user_id: str, display_name: str, secret: str) -> tuple:
    """Create a JWT token"""
    import jwt

    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "display_name": display_name,
        "exp": expires,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return token, expires


def cmd_setup():
    """First-time setup - set password for Daedalus"""
    user_manager = UserManager(storage_dir=str(DATA_DIR / "users"))

    profile = user_manager.load_profile(DAEDALUS_USER_ID)
    if not profile:
        print(f"Error: Daedalus user not found (ID: {DAEDALUS_USER_ID})")
        print("Create the user first via the API or manually.")
        sys.exit(1)

    print(f"Setting up authentication for: {profile.display_name}")
    print(f"User ID: {profile.user_id}")

    # Generate a secure password
    password = secrets.token_urlsafe(32)

    # Set the password
    success = user_manager.set_admin_password(DAEDALUS_USER_ID, password)
    if not success:
        print("Error: Failed to set password")
        sys.exit(1)

    # Save credentials
    creds = load_credentials()
    creds.update({
        "user_id": DAEDALUS_USER_ID,
        "display_name": profile.display_name,
        "password": password,
        "setup_at": datetime.now().isoformat(),
    })
    save_credentials(creds)

    print(f"\nCredentials saved to: {CREDENTIALS_FILE}")
    print("Password has been auto-generated and stored securely.")

    # Generate initial token
    secret = get_jwt_secret()
    token, expires = create_token(DAEDALUS_USER_ID, profile.display_name, secret)

    creds["token"] = token
    creds["token_expires"] = expires.isoformat()
    save_credentials(creds)

    print(f"\nInitial token generated (expires: {expires.isoformat()})")
    print("\nSetup complete!")


def cmd_token():
    """Get or refresh auth token"""
    creds = load_credentials()

    if "password" not in creds:
        print("Error: Daedalus not set up. Run: python scripts/daedalus_auth.py setup")
        sys.exit(1)

    # Check if existing token is still valid
    if "token_expires" in creds:
        expires = datetime.fromisoformat(creds["token_expires"])
        if expires > datetime.utcnow() + timedelta(hours=1):
            # Token still good for at least an hour
            print(f"Token: {creds['token']}")
            print(f"Expires: {creds['token_expires']}")
            return

    # Generate new token
    secret = get_jwt_secret()
    token, expires = create_token(
        creds["user_id"],
        creds["display_name"],
        secret
    )

    creds["token"] = token
    creds["token_expires"] = expires.isoformat()
    save_credentials(creds)

    print(f"Token: {token}")
    print(f"Expires: {expires.isoformat()}")


def cmd_info():
    """Show Daedalus user info"""
    user_manager = UserManager(storage_dir=str(DATA_DIR / "users"))
    profile = user_manager.load_profile(DAEDALUS_USER_ID)

    if not profile:
        print(f"Error: Daedalus user not found (ID: {DAEDALUS_USER_ID})")
        sys.exit(1)

    print(f"Display Name: {profile.display_name}")
    print(f"User ID: {profile.user_id}")
    print(f"Relationship: {profile.relationship}")
    print(f"Created: {profile.created_at}")
    print(f"Is Admin: {profile.is_admin}")
    print(f"Has Password: {profile.password_hash is not None}")

    if profile.background:
        print(f"\nBackground:")
        for k, v in profile.background.items():
            print(f"  {k}: {v}")

    creds = load_credentials()
    if "token_expires" in creds:
        print(f"\nToken Expires: {creds['token_expires']}")


def cmd_export():
    """Export token in a format easy to use"""
    creds = load_credentials()

    if "token" not in creds:
        print("Error: No token. Run: python scripts/daedalus_auth.py token")
        sys.exit(1)

    # Output just the token for easy capture
    print(creds["token"])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "setup":
        cmd_setup()
    elif cmd == "token":
        cmd_token()
    elif cmd == "info":
        cmd_info()
    elif cmd == "export":
        cmd_export()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
