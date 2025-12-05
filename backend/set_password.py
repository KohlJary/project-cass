#!/usr/bin/env python3
"""
Utility script to set a password for an existing user account.
Usage: python set_password.py <user_id> <email> <password>
"""
import sys
import json
from datetime import datetime
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from auth import hash_password

def main():
    if len(sys.argv) != 4:
        print("Usage: python set_password.py <user_id> <email> <password>")
        print("\nKnown users:")
        index_path = Path("data/users/index.json")
        if index_path.exists():
            with open(index_path) as f:
                users = json.load(f)
            for uid, name in users.items():
                print(f"  {uid}: {name}")
        sys.exit(1)

    user_id = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]

    user_dir = Path(f"data/users/{user_id}")
    if not user_dir.exists():
        print(f"Error: User directory not found: {user_dir}")
        sys.exit(1)

    # Create auth.json
    auth_data = {
        "email": email.lower(),
        "password_hash": hash_password(password),
        "created_at": datetime.now().isoformat(),
        "last_login": None
    }

    auth_path = user_dir / "auth.json"
    with open(auth_path, 'w') as f:
        json.dump(auth_data, f, indent=2)

    print(f"Password set for user {user_id}")
    print(f"Email: {email}")
    print(f"Auth file: {auth_path}")

if __name__ == "__main__":
    main()
