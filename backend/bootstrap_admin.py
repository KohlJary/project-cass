#!/usr/bin/env python3
"""
Bootstrap script to create the initial admin user.
Run this once to set up admin access for the first user.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from users import UserManager
from getpass import getpass

def main():
    manager = UserManager("./data/users")

    # List users
    users = manager.list_users()
    if not users:
        print("No users found. Create a user first.")
        return

    print("\nAvailable users:")
    for i, user in enumerate(users):
        profile = manager.load_profile(user["user_id"])
        admin_status = " (admin)" if profile and profile.is_admin else ""
        print(f"  {i + 1}. {user['display_name']}{admin_status}")

    print()
    choice = input("Enter user number to make admin (or 'q' to quit): ").strip()

    if choice.lower() == 'q':
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(users):
            print("Invalid choice")
            return
    except ValueError:
        print("Invalid input")
        return

    user = users[idx]
    user_id = user["user_id"]
    display_name = user["display_name"]

    # Set admin status
    manager.set_admin_status(user_id, True)
    print(f"\n{display_name} is now an admin.")

    # Set password
    password = getpass(f"Enter password for {display_name}: ")
    if password:
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("Passwords don't match!")
            return

        manager.set_admin_password(user_id, password)
        print(f"Password set for {display_name}.")
    else:
        print("No password set (skipped).")

    print(f"\nDone! {display_name} can now log in to the admin dashboard.")

if __name__ == "__main__":
    main()
