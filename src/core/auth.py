from config.settings import settings
from src.core.exceptions import ECommerceMCPError

class UnauthorizedError(ECommerceMCPError):
    """Raised when authentication fails in SSE/HTTP deployment mode."""
    pass

def check_api_key(auth_header: str | None) -> None:
    """
    Checks the provided API key against the server configuration.
    Supports both direct keys and 'Bearer <token>' headers.
    
    Raises UnauthorizedError if authentication fails.
    """
    expected_key = settings.api_key
    # If no API key is configured in settings, security is disabled
    if not expected_key:
        return
        
    if not auth_header:
        raise UnauthorizedError(
            "API Access Denied: Missing authentication token. "
            "Please provide a valid token in the Authorization or X-API-Key header."
        )
        
    provided_key = auth_header.strip()
    
    # Handle Bearer token prefix if present
    if provided_key.lower().startswith("bearer "):
        provided_key = provided_key[7:].strip()
        
    if provided_key != expected_key.strip():
        raise UnauthorizedError("API Access Denied: Invalid authentication credentials.")
