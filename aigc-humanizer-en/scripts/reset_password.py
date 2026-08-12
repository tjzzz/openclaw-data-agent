#!/usr/bin/env python3
"""
Reset password for a user in the local database.
Usage:
    python reset_password.py zzz216@yeah.net NewPassword123
"""

import sys
import os
import sqlite3
from datetime import datetime, timezone

# Ensure we're in the project root
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

DB_PATH = os.path.join(project_root, 'instance', 'aigc_humanizer.db')

from werkzeug.security import generate_password_hash


def main():
    if len(sys.argv) != 3:
        print("Usage: python reset_password.py <email> <new_password>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    new_password = sys.argv[2]

    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        print("Make sure you're in the project root directory.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Check user exists
    cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        print(f"User '{email}' not found in database.")
        conn.close()
        sys.exit(1)

    print(f"Found user: id={user['id']}, email={user['email']}, created_at={user['created_at']}")

    # Generate new password hash
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE email = ?",
        (password_hash, email)
    )
    conn.commit()
    conn.close()

    print(f"\n✅ Password for '{email}' has been reset successfully!")
    print(f"   New password: {new_password}")
    print("\nYou can now log in with the new password.")


if __name__ == '__main__':
    main()