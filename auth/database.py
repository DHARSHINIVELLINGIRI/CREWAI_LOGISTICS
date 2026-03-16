"""
Auth Database — SQLite schema + connection management.
Creates the database file at {project_root}/data/eshipz_auth.db on first run.
"""

import sqlite3
import os
import hashlib
import secrets
import datetime

# ── DB path ───────────────────────────────────────────────────────────────────
_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(_ROOT, "data")
DB_PATH= os.path.join(DB_DIR, "eshipz_auth.db")

os.makedirs(DB_DIR, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    """Return a thread-safe connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    name         TEXT     NOT NULL,
    email        TEXT     UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    salt         TEXT     NOT NULL,
    role         TEXT     NOT NULL DEFAULT 'user',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_shipments (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    tracking_id  TEXT     NOT NULL,
    user_id      INTEGER  NOT NULL,
    source       TEXT,
    destination  TEXT,
    weight       REAL,
    priority     TEXT,
    carrier      TEXT,
    awb          TEXT,
    status       TEXT     DEFAULT 'Booked',
    agent_output TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_shipments_user  ON user_shipments(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);
"""

def init_db():
    """Create tables and seed default admin account."""
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    # Seed admin if not exists
    cur = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@eshipz.com",))
    if cur.fetchone() is None:
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256((salt + "Admin@123").encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (name, email, password_hash, salt, role) VALUES (?,?,?,?,?)",
            ("System Admin", "admin@eshipz.com", pw_hash, salt, "admin")
        )
        conn.commit()

    # Migrate: add awb column to existing databases safely
    try:
        conn.execute("ALTER TABLE user_shipments ADD COLUMN awb TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists — safe to ignore

    conn.close()


# Initialise on import
init_db()
