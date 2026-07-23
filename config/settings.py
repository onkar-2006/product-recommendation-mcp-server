import sys
import os
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

def _default_db_path() -> str:
    # If running in Linux/cloud environment, write cache to writable /tmp
    if sys.platform != "win32" or "FASTMCP_USER_ENTRYPOINT" in os.environ:
        return "/tmp/mcp_cache.db"
    return "data/mcp_cache.db"

def _default_log_file() -> str | None:
    # If running in Linux/cloud environment, write logs to writable /tmp
    if sys.platform != "win32" or "FASTMCP_USER_ENTRYPOINT" in os.environ:
        return "/tmp/mcp.log"
    return "logs/mcp.log"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Server configuration
    transport: Literal["stdio", "sse"] = Field(
        default="stdio", 
        description="MCP communication transport (stdio for local, sse for remote/deployed)"
    )
    host: str = Field(default="0.0.0.0", description="Host to bind for SSE server")
    port: int = Field(default=8000, description="Port to bind for SSE server")
    api_key: str | None = Field(
        default=None, 
        description="API Key token for securing the SSE server. If set, clients must send Bearer headers."
    )
    
    # Playwright scraper configuration
    headless: bool = Field(
        default=True, 
        description="Run browser in headless mode. Set to False for local troubleshooting."
    )
    proxy_server: str | None = Field(
        default=None, 
        description="Proxy server address (e.g. http://myproxy.com:8000)"
    )
    proxy_username: str | None = Field(default=None, description="Username for proxy auth")
    proxy_username: str | None = Field(default=None, description="Username for proxy auth")
    proxy_password: str | None = Field(default=None, description="Password for proxy auth")
    
    timeout_ms: int = Field(default=30000, description="Global page navigation & wait timeout in ms")
    stealth_mode: bool = Field(default=True, description="Enable Playwright stealth browser profile overrides")
    max_concurrent_contexts: int = Field(
        default=5, 
        description="Maximum concurrent browser tabs/contexts to open to prevent memory saturation."
    )
    
    # System logs
    log_level: str = Field(default="INFO", description="Standard logging level (DEBUG, INFO, WARNING, ERROR)")
    log_file: str | None = Field(default_factory=_default_log_file, description="Path to persistent log file. Set to None to disable.")
    
    # SQLite cache & database persistence
    sqlite_db_path: str = Field(default_factory=_default_db_path, description="Path to local SQLite cache database file")
    cache_enabled: bool = Field(default=True, description="Toggles cache check layer")
    cache_ttl_search_seconds: int = Field(default=600, description="Search result cache lifetime (default 10 mins)")
    cache_ttl_details_seconds: int = Field(default=86400, description="Deep specs cache lifetime (default 24 hours)")

# Singleton settings instance
settings = Settings()
