import pytest
from src.core.browser import browser_manager

# Configure pytest-asyncio to handle async tests
pytestmark = pytest.mark.asyncio

async def test_browser_manager_singleton():
    """Verifies that multiple calls to get_browser return the same singleton instance."""
    browser1 = await browser_manager.get_browser()
    browser2 = await browser_manager.get_browser()
    
    assert browser1 is not None
    assert browser2 is not None
    assert browser1 == browser2
    assert browser1.is_connected() is True

async def test_page_context_creation_and_navigation():
    """Verifies that page_context yields a valid Page and performs basic navigation."""
    async with browser_manager.page_context() as page:
        assert page is not None
        # Verify page state
        await page.goto("about:blank")
        url = page.url
        assert url == "about:blank"
        
        # Verify stealth script injected successfully (webdriver override check)
        webdriver_val = await page.evaluate("navigator.webdriver")
        assert webdriver_val is None or webdriver_val is False
