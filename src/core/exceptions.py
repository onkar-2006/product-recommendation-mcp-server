class ECommerceMCPError(Exception):
    """Base exception class for all errors in the ECommerce MCP system."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BrowserInitializationError(ECommerceMCPError):
    """Raised when Playwright fails to initialize or spin up a browser context."""
    pass


class ScrapingBlockedError(ECommerceMCPError):
    """Raised when an e-commerce platform blocks our scraper (e.g., CAPTCHA, HTTP 403, Cloudflare challenge)."""
    pass


class ProductNotFoundError(ECommerceMCPError):
    """Raised when a search query yields no items, or a product details URL returns a 404."""
    pass


class PlatformNotSupportedError(ECommerceMCPError):
    """Raised when a tool request targets an unsupported e-commerce platform."""
    pass


class DatabaseError(ECommerceMCPError):
    """Raised when SQLite operations (read, write, schema generation) fail."""
    pass
