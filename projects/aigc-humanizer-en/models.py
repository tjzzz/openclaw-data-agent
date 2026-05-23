#!/usr/bin/env python3
"""
Data models for AI Humanizer.
SQLite database operations using sqlite3 module.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_DIR = os.path.join(os.path.dirname(__file__), 'instance')
DB_PATH = os.path.join(DB_DIR, 'aigc_humanizer.db')


def get_connection():
    """Get a new SQLite database connection."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database and create all tables."""
    conn = get_connection()
    try:
        User.init_table(conn)
        Order.init_table(conn)
    finally:
        conn.close()


class User:
    """User model — class methods for database operations."""

    @classmethod
    def init_table(cls, conn):
        """Create the users table if it does not exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

    @classmethod
    def create(cls, conn, email, password):
        """Create a new user. Password is hashed via werkzeug.security."""
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        created_at = datetime.utcnow().isoformat()
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, created_at)
        )
        conn.commit()
        return cls.get_by_id(conn, cursor.lastrowid)

    @classmethod
    def get_by_email(cls, conn, email):
        """Look up a user by email. Returns dict or None."""
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def get_by_id(cls, conn, user_id):
        """Look up a user by primary key. Returns dict or None."""
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def verify_password(cls, conn, email, password):
        """Verify password for a given email. Returns user dict or None."""
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row and check_password_hash(row['password_hash'], password):
            return dict(row)
        return None


class Order:
    """Order model — class methods for database operations."""

    @classmethod
    def init_table(cls, conn):
        """Create the orders table if it does not exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_id TEXT UNIQUE NOT NULL,
                original_text TEXT NOT NULL,
                rewritten_text TEXT NOT NULL,
                original_format TEXT DEFAULT 'txt',
                original_filename TEXT,
                word_count INTEGER,
                price REAL,
                mode TEXT DEFAULT 'academic',
                original_score REAL,
                rewritten_score REAL,
                status TEXT DEFAULT 'completed',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()

    @classmethod
    def create(cls, conn, user_id, order_id, original_text, rewritten_text,
               original_format, original_filename, word_count, price, mode,
               original_score, rewritten_score):
        """Create a new order record."""
        created_at = datetime.utcnow().isoformat()
        expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
        conn.execute(
            """INSERT INTO orders
               (user_id, order_id, original_text, rewritten_text,
                original_format, original_filename, word_count, price, mode,
                original_score, rewritten_score, status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)""",
            (user_id, order_id, original_text, rewritten_text,
             original_format, original_filename, word_count, price, mode,
             original_score, rewritten_score, created_at, expires_at)
        )
        conn.commit()

    @classmethod
    def get_by_user_id(cls, conn, user_id, page=1, per_page=10):
        """Get paginated orders for a user. Returns (orders_list, total_count)."""
        # Get total count
        count_row = conn.execute(
            "SELECT COUNT(*) as total FROM orders WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        total = count_row['total'] if count_row else 0

        # Get page
        offset = (page - 1) * per_page
        cursor = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, per_page, offset)
        )
        orders = [dict(row) for row in cursor.fetchall()]
        return orders, total

    @classmethod
    def get_by_order_id(cls, conn, order_id):
        """Look up an order by order_id. Returns dict or None."""
        cursor = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @classmethod
    def update_rewrite(cls, conn, order_id, rewritten_text, rewritten_score):
        """Update the rewritten text and score for an existing order."""
        conn.execute(
            "UPDATE orders SET rewritten_text = ?, rewritten_score = ? WHERE order_id = ?",
            (rewritten_text, rewritten_score, order_id)
        )
        conn.commit()

    @classmethod
    def get_by_session(cls, conn, order_id):
        """Look up an order by order_id (for unauthenticated session access)."""
        cursor = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
