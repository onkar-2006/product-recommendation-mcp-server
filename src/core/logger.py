import logging
import sys
import os
from config.settings import settings

def setup_logging() -> None:
    """
    Configures application logging.
    Crucially, it forces all console logs to write to sys.stderr (instead of sys.stdout).
    This ensures that in MCP STDIO transport mode, logs do not pollute the JSON-RPC
    stdout stream which would cause the client connection to crash.
    """
    # Initialize directory for persistent log files if specified
    if settings.log_file:
        try:
            log_dir = os.path.dirname(settings.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"WARNING: Could not create log directory {log_dir}: {e}. Falling back to /tmp/mcp.log\n")
            settings.log_file = "/tmp/mcp.log"

    log_format = "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s"
    formatter = logging.Formatter(log_format)

    # Configure root logger
    root_logger = logging.getLogger()
    
    # Remove any default handlers to prevent duplicate logs or default stdout redirection
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set overall logging level
    numeric_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # 1. Console Handler: Directs output to STDERR, making it STDIO-transport safe.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    root_logger.addHandler(console_handler)

    # 2. File Handler: Persists logs if configured in settings
    if settings.log_file:
        try:
            file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(numeric_level)
            root_logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"WARNING: Could not initialize log file handler for {settings.log_file}: {e}. Trying fallback to /tmp/mcp.log\n")
            try:
                settings.log_file = "/tmp/mcp.log"
                file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
                file_handler.setFormatter(formatter)
                file_handler.setLevel(numeric_level)
                root_logger.addHandler(file_handler)
            except Exception as ex:
                sys.stderr.write(f"WARNING: Could not initialize log file handler in /tmp: {ex}. Persistent logging disabled.\n")

    # Mute/redirect third party libraries that might pollute stdout
    logging.getLogger("pyee").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    
    # Uvicorn logging redirects (for SSE mode)
    for uvicorn_logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers = []
        uv_logger.propagate = True

    root_logger.info("Logging successfully initialized. All console logs routed to STDERR.")

# Run setup when imported to ensure early configuration
setup_logging()
logger = logging.getLogger("ecommerce-mcp")
