import hashlib
import json
import asyncio
from datetime import datetime, timedelta
from typing import Any
from config.settings import settings
from src.core.db import get_db_connection
from src.core.logger import logger

def _hash_key(key: str) -> str:
    """Helper to generate a SHA-256 hex digest of a key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def _get_search_sync(platform: str, query: str, limit: int) -> str | None:
    query_key = f"search:{platform}:{query.lower().strip()}:{limit}"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Fetch matching record
        cursor.execute(
            "SELECT results_json, created_at FROM search_cache WHERE query_key = ?", 
            (query_key,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        # Check TTL
        created_at = datetime.fromisoformat(row["created_at"])
        age = datetime.utcnow() - created_at
        if age > timedelta(seconds=settings.cache_ttl_search_seconds):
            # Expired, delete it
            cursor.execute("DELETE FROM search_cache WHERE query_key = ?", (query_key,))
            conn.commit()
            return None
            
        return row["results_json"]
    except Exception as e:
        logger.warning(f"Error fetching from search cache: {e}")
        return None
    finally:
        conn.close()

def _set_search_sync(platform: str, query: str, limit: int, results_json: str) -> None:
    query_key = f"search:{platform}:{query.lower().strip()}:{limit}"
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache (query_key, results_json, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (query_key, results_json)
            )
    except Exception as e:
        logger.warning(f"Error writing to search cache: {e}")
    finally:
        conn.close()

def _get_details_sync(url: str) -> str | None:
    url_hash = _hash_key(url.strip())
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT details_json, created_at FROM details_cache WHERE url_hash = ?", 
            (url_hash,)
        )
        row = cursor.fetchone()
        if not row:
            return None
            
        # Check TTL
        created_at = datetime.fromisoformat(row["created_at"])
        age = datetime.utcnow() - created_at
        if age > timedelta(seconds=settings.cache_ttl_details_seconds):
            # Expired, delete it
            cursor.execute("DELETE FROM details_cache WHERE url_hash = ?", (url_hash,))
            conn.commit()
            return None
            
        return row["details_json"]
    except Exception as e:
        logger.warning(f"Error fetching from details cache: {e}")
        return None
    finally:
        conn.close()

def _set_details_sync(url: str, details_json: str) -> None:
    url_hash = _hash_key(url.strip())
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO details_cache (url_hash, url, details_json, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (url_hash, url, details_json)
            )
    except Exception as e:
        logger.warning(f"Error writing to details cache: {e}")
    finally:
        conn.close()

def _get_session_sync(platform: str) -> tuple[str, str | None] | None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cookies_json, headers_json FROM session_cache WHERE platform = ?", 
            (platform,)
        )
        row = cursor.fetchone()
        if row:
            return row["cookies_json"], row["headers_json"]
        return None
    except Exception as e:
        logger.warning(f"Error fetching session cache: {e}")
        return None
    finally:
        conn.close()

def _set_session_sync(platform: str, cookies_json: str, headers_json: str | None) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO session_cache (platform, cookies_json, headers_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (platform, cookies_json, headers_json)
            )
    except Exception as e:
        logger.warning(f"Error writing session cache: {e}")
    finally:
        conn.close()

def _clear_expired_sync() -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Calculate cutoffs
        search_cutoff = (datetime.utcnow() - timedelta(seconds=settings.cache_ttl_search_seconds)).isoformat()
        details_cutoff = (datetime.utcnow() - timedelta(seconds=settings.cache_ttl_details_seconds)).isoformat()
        
        with conn:
            cursor.execute("DELETE FROM search_cache WHERE created_at < ?", (search_cutoff,))
            cursor.execute("DELETE FROM details_cache WHERE created_at < ?", (details_cutoff,))
            
        logger.info("Cleared expired cache database records.")
    except Exception as e:
        logger.warning(f"Error during expired cache cleaning: {e}")
    finally:
        conn.close()

# Public Async API Abstractions

async def get_search_cache(platform: str, query: str, limit: int) -> list[dict[str, Any]] | None:
    """Retrieves search query results from cache if enabled and valid."""
    if not settings.cache_enabled:
        return None
    raw = await asyncio.to_thread(_get_search_sync, platform, query, limit)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None

async def set_search_cache(platform: str, query: str, limit: int, results: list[dict[str, Any]]) -> None:
    """Saves search query results to the SQLite cache."""
    if not settings.cache_enabled:
        return
    results_json = json.dumps(results)
    await asyncio.to_thread(_set_search_sync, platform, query, limit, results_json)

async def get_details_cache(url: str) -> dict[str, Any] | None:
    """Retrieves deep product details from cache if enabled and valid."""
    if not settings.cache_enabled:
        return None
    raw = await asyncio.to_thread(_get_details_sync, url)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None

async def set_details_cache(url: str, details: dict[str, Any]) -> None:
    """Saves deep product details to the SQLite cache."""
    if not settings.cache_enabled:
        return
    details_json = json.dumps(details)
    await asyncio.to_thread(_set_details_sync, url, details_json)

async def get_session_cache(platform: str) -> tuple[list[dict[str, Any]], dict[str, str] | None] | None:
    """Retrieves stored cookies and extra headers for a specific platform."""
    res = await asyncio.to_thread(_get_session_sync, platform)
    if res:
        cookies_raw, headers_raw = res
        try:
            cookies = json.loads(cookies_raw)
            headers = json.loads(headers_raw) if headers_raw else None
            return cookies, headers
        except Exception:
            return None
    return None

async def set_session_cache(platform: str, cookies: list[dict[str, Any]], headers: dict[str, str] | None = None) -> None:
    """Stores platform session cookies and extra headers."""
    cookies_json = json.dumps(cookies)
    headers_json = json.dumps(headers) if headers else None
    await asyncio.to_thread(_set_session_sync, platform, cookies_json, headers_json)

async def clear_expired_cache() -> None:
    """Evicts expired records from the SQLite database."""
    await asyncio.to_thread(_clear_expired_sync)
