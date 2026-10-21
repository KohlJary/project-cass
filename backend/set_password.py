#!/usr/bin/env python3
"""
Set the login email and password for an existing user.
Usage: python set_password.py <user_id> <email> <password>

Since #61 there is one credential store, the SQLite users table, and this
writes there (users.email, users.password_hash). It used to write
DATA_DIR/users/<id>/auth.json, which is now read only as a transition fallback.
"""
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def main():
    from database import get_db
    from auth import hash_password

    if len(sys.argv) != 4:
        print("Usage: python set_password.py <user_id> <email> <password>")
        print("\nKnown users:")
        with get_db() as conn:
            for row in conn.execute("SELECT id, display_name FROM users ORDER BY created_at"):
                print(f"  {row[0]}: {row[1]}")
        sys.exit(1)

    user_id, email, password = sys.argv[1], sys.argv[2], sys.argv[3]

    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE users SET email = ?, password_hash = ?, updated_at = ? WHERE id = ?",
            (email.lower(), hash_password(password), datetime.now().isoformat(), user_id),
        )
        if cursor.rowcount == 0:
            print(f"Error: no user with id {user_id}")
            sys.exit(1)

    print(f"Password set for user {user_id}")
    print(f"Email: {email}")


if __name__ == "__main__":
    main()
