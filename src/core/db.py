import sqlite3
import os
import asyncio
from config.settings import settings
from src.core.logger import logger
from src.core.exceptions import DatabaseError

DB_INITIALIZATION_SQL = """
CREATE TABLE IF NOT EXISTS search_cache (
    query_key TEXT PRIMARY KEY,
    results_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS details_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_cache (
    platform TEXT PRIMARY KEY,
    cookies_json TEXT NOT NULL,
    headers_json TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_created ON search_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_details_created ON details_cache(created_at);
"""

def init_db_sync() -> None:
    """Synchronous database connection setup and table creation."""
    db_path = settings.sqlite_db_path
    
    # Ensure parent data directory exists
    db_dir = os.path.dirname(db_path)
    try:
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create database directory {db_dir}: {e}. Falling back to /tmp/mcp_cache.db")
        settings.sqlite_db_path = "/tmp/mcp_cache.db"
        db_path = settings.sqlite_db_path
        
    try:
        conn = sqlite3.connect(db_path)
        # Enable WAL mode for parallel read/write performance
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        with conn:
            conn.executescript(DB_INITIALIZATION_SQL)
            
        conn.close()
        logger.info(f"SQLite database initialized successfully at {db_path} in WAL mode.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database at {db_path}: {e}")
        raise DatabaseError(f"Database initialization failed: {e}")

async def init_db() -> None:
    """Asynchronous initialization wrapper."""
    await asyncio.to_thread(init_db_sync)

def get_db_connection() -> sqlite3.Connection:
    """
    Returns a standard synchronous sqlite3 connection configured withWAL options.
    Should be used inside asyncio.to_thread for thread-safety.
    """
    try:
        conn = sqlite3.connect(settings.sqlite_db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to SQLite database: {e}")
        raise DatabaseError(f"Database connection error: {e}")
