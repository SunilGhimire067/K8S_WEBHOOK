"""
Shared MySQL database module for Sentinel K8s.

Provides connection pooling and helpers used by:
  - webhook_receiver.py
  - mcp_server.py
  - chat_ui/backend/events_api.py
  - chat_ui/backend/auth.py
  - chat_ui/backend/config.py
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger("database")

# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "sentinel")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "sentinel_pass")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "sentinel_k8s")

_pool: pooling.MySQLConnectionPool | None = None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="sentinel_pool",
            pool_size=5,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=False,
        )
    return _pool


def get_db() -> mysql.connector.MySQLConnection:
    """Return a connection from the pool."""
    return _get_pool().get_connection()


def get_cursor(conn: mysql.connector.MySQLConnection):
    """Return a dictionary cursor for the given connection."""
    return conn.cursor(dictionary=True)


def wait_for_db(timeout: int = 60, interval: int = 2) -> None:
    """Block until MySQL is reachable or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
            )
            conn.close()
            logger.info("MySQL is ready at %s:%s", MYSQL_HOST, MYSQL_PORT)
            return
        except mysql.connector.Error:
            logger.info("Waiting for MySQL at %s:%s …", MYSQL_HOST, MYSQL_PORT)
            time.sleep(interval)
    raise RuntimeError(f"MySQL not reachable after {timeout}s")


def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    cursor = conn.cursor()

    # --- k8s_events ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS k8s_events (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            event_id    VARCHAR(64) NOT NULL UNIQUE,
            event_type  VARCHAR(32) NOT NULL,
            kind        VARCHAR(64),
            name        VARCHAR(253),
            namespace   VARCHAR(253),
            reason      VARCHAR(128),
            message     TEXT,
            severity    VARCHAR(16) DEFAULT 'info',
            raw_payload LONGTEXT NOT NULL,
            status      VARCHAR(16) DEFAULT 'new',
            analysis    TEXT,
            created_at  VARCHAR(64) NOT NULL,
            updated_at  VARCHAR(64) NOT NULL
        )
    """)
    # MySQL doesn't support CREATE INDEX IF NOT EXISTS — check first
    for idx_name, idx_col in [
        ("idx_status", "status"),
        ("idx_severity", "severity"),
        ("idx_created", "created_at"),
    ]:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = %s AND table_name = 'k8s_events' AND index_name = %s",
            (MYSQL_DATABASE, idx_name),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"CREATE INDEX {idx_name} ON k8s_events({idx_col})")

    # --- app_config ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            config_key   VARCHAR(128) PRIMARY KEY,
            config_value TEXT NOT NULL,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    # --- users ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            username      VARCHAR(128) NOT NULL UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            totp_secret   VARCHAR(64),
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- sessions ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token      VARCHAR(128) PRIMARY KEY,
            username   VARCHAR(128) NOT NULL,
            is_temp    BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            INDEX idx_expires (expires_at)
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Database tables initialized")


# ---------------------------------------------------------------------------
# ConfigStore — read/write app_config with in-memory TTL cache
# ---------------------------------------------------------------------------

class ConfigStore:
    """Key-value config backed by MySQL app_config table with 60s cache."""

    _cache: dict[str, tuple[str, float]] = {}  # key -> (value, expiry_timestamp)
    _TTL = 60  # seconds

    def get(self, key: str, default: str = "") -> str:
        now = time.time()
        cached = self._cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
        try:
            conn = get_db()
            cursor = get_cursor(conn)
            cursor.execute(
                "SELECT config_value FROM app_config WHERE config_key = %s", (key,)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                self._cache[key] = (row["config_value"], now + self._TTL)
                return row["config_value"]
        except Exception:
            logger.exception("ConfigStore.get failed for key=%s", key)
        return default

    def set(self, key: str, value: str) -> None:
        try:
            conn = get_db()
            cursor = get_cursor(conn)
            cursor.execute(
                "INSERT INTO app_config (config_key, config_value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)",
                (key, value),
            )
            conn.commit()
            cursor.close()
            conn.close()
            self._cache[key] = (value, time.time() + self._TTL)
        except Exception:
            logger.exception("ConfigStore.set failed for key=%s", key)


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def get_user(username: str) -> dict | None:
    """Fetch a user row by username, or None."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def update_user_totp(username: str, totp_secret: str) -> None:
    """Store verified TOTP secret for a user."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute(
        "UPDATE users SET totp_secret = %s WHERE username = %s",
        (totp_secret, username),
    )
    conn.commit()
    cursor.close()
    conn.close()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def create_session(token: str, username: str, is_temp: bool = False,
                   ttl_seconds: int = 86400) -> None:
    """Insert a session row with a TTL."""
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute(
        "INSERT INTO sessions (token, username, is_temp, expires_at) "
        "VALUES (%s, %s, %s, %s)",
        (token, username, is_temp, expires),
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_session(token: str, temp_only: bool = False) -> dict | None:
    """Fetch a valid (non-expired) session. Optionally filter temp-only."""
    conn = get_db()
    cursor = get_cursor(conn)
    sql = "SELECT * FROM sessions WHERE token = %s AND expires_at > NOW()"
    if temp_only:
        sql += " AND is_temp = TRUE"
    else:
        sql += " AND is_temp = FALSE"
    cursor.execute(sql, (token,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def delete_session(token: str) -> None:
    """Delete a session by token."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("DELETE FROM sessions WHERE token = %s", (token,))
    conn.commit()
    cursor.close()
    conn.close()


def cleanup_expired_sessions() -> int:
    """Delete all expired sessions. Returns count deleted."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("DELETE FROM sessions WHERE expires_at < NOW()")
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    if deleted:
        logger.info("Cleaned up %d expired sessions", deleted)
    return deleted


# ---------------------------------------------------------------------------
# Seed admin user + default config
# ---------------------------------------------------------------------------

def seed_admin_user(password: str = "admin") -> None:
    """Create admin user and default LLM config if they don't exist yet."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Check if admin user already exists
    cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE username = 'admin'")
    if cursor.fetchone()["cnt"] == 0:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            ("admin", hashed),
        )
        logger.info("Seeded admin user")

    # Seed default LLM config values (INSERT IGNORE keeps existing values)
    defaults = {
        "litellm_base_url": "http://host.docker.internal:4000/v1",
        "litellm_model": "gpt-4o",
        "litellm_api_key": "sk-placeholder",
    }
    for key, value in defaults.items():
        cursor.execute(
            "INSERT IGNORE INTO app_config (config_key, config_value) VALUES (%s, %s)",
            (key, value),
        )

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Seed data verified")
