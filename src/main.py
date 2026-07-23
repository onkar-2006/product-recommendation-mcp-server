import sys
import os
import argparse
import asyncio
from contextlib import asynccontextmanager

# Resolve pythonpath mapping when running or inspecting this script directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastmcp import FastMCP
from config.settings import settings
from src.core.logger import logger
from src.core.db import init_db
from src.core.browser import browser_manager
from src.schemas.product import Product, CompareResult, ProductDetails
from src.tools.search import search_products_logic
from src.tools.compare import compare_prices_logic
from src.tools.details import get_product_details_logic

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Initializes system dependencies on startup and cleans them up on shutdown."""
    logger.info("Starting up ECommerce MCP Server...")
    # Init Cache DB tables
    await init_db()
    # Warm up browser manager/process
    try:
        await browser_manager.get_browser()
        logger.info("Stealth Browser Pool pre-warmed successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Browser manager failed to warm up on startup: {e}")
        
    yield
    
    logger.info("Shutting down ECommerce MCP Server...")
    await browser_manager.close()

# Create the primary FastMCP Server instance with lifespan context
mcp = FastMCP("ECommerce-MCP-Server", lifespan=app_lifespan)

# 1. MCP Tools Registrations

@mcp.tool(name="search_products", description="Search products across one or more e-commerce platforms (amazon, flipkart, meesho, myntra) in parallel.")
async def search_products(
    query: str,
    platforms: list[str] = ["amazon", "flipkart", "meesho", "myntra"],
    limit: int = 5
) -> list[Product]:
    """Search products across platforms in parallel."""
    try:
        return await search_products_logic(query, platforms, limit)
    except Exception as e:
        logger.error(f"Error in search_products tool: {e}")
        # Re-raise so the protocol sends the error message back to the LLM
        raise

@mcp.tool(name="compare_prices", description="Query multiple e-commerce sites for a product and return a ranked comparison list from cheapest to most expensive.")
async def compare_prices(
    query: str,
    platforms: list[str] = ["amazon", "flipkart", "meesho", "myntra"]
) -> CompareResult:
    """Compare prices across platforms."""
    try:
        return await compare_prices_logic(query, platforms)
    except Exception as e:
        logger.error(f"Error in compare_prices tool: {e}")
        raise

@mcp.tool(name="get_product_details", description="Retrieve detailed specifications, images, pricing, and seller name for a direct product URL.")
async def get_product_details(
    url: str,
    platform: str
) -> ProductDetails:
    """Get deep specifications for a product URL."""
    try:
        return await get_product_details_logic(url, platform)
    except Exception as e:
        logger.error(f"Error in get_product_details tool: {e}")
        raise

# Lifecycle events managed by app_lifespan context manager above

# 3. Main CLI Runner

def main():
    parser = argparse.ArgumentParser(description="ECommerce MCP Server Launcher")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=settings.transport,
        help="MCP communication transport channel (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default=settings.host,
        help="Host address to bind for SSE server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help="Port number to bind for SSE server (default: 8000)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=settings.headless,
        help="Force run Chromium in headless mode"
    )
    parser.add_argument(
        "--headful",
        action="store_false",
        dest="headless",
        help="Run Chromium in headful mode (UI visible)"
    )
    
    args = parser.parse_args()
    
    # Apply CLI argument overrides to settings
    settings.transport = args.transport
    settings.host = args.host
    settings.port = args.port
    settings.headless = args.headless

    logger.info(f"Launching ECommerce MCP server with transport={settings.transport.upper()} headless={settings.headless}")
    
    if settings.transport == "stdio":
        # Run local STDIO server
        mcp.run(transport="stdio")
    elif settings.transport == "sse":
        # Run deployed SSE server using built-in SSE capabilities on host and port
        mcp.run(transport="sse", host=settings.host, port=settings.port)

if __name__ == "__main__":
    main()
