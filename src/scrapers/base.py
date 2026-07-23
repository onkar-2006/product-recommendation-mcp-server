import re
import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Optional, Any
from playwright.async_api import Page, Response
from tenacity import AsyncRetrying, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from src.schemas.product import Product, ProductDetails
from src.core.exceptions import ScrapingBlockedError, ProductNotFoundError
from src.core.logger import logger

class BaseScraper(ABC):
    """
    Abstract base scraper class providing common interfaces and utility functions 
    for e-commerce target extractions. Includes anti-bot humanization and retry layers.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> List[Product]:
        """Performs a product search on the platform and returns a list of items."""
        pass

    @abstractmethod
    async def get_details(self, url: str) -> ProductDetails:
        """Navigates to a specific product detail page and returns expanded specifications."""
        pass

    # Core Helpers & Utility Methods

    async def human_like_scroll(self, page: Page, max_scrolls: int = 3) -> None:
        """
        Scrolls the page down incrementally, pausing randomly to emulate human scanning behavior.
        Triggers lazy-loaded elements (especially images and dynamic React grids).
        """
        try:
            for i in range(max_scrolls):
                # Calculate randomized scroll increments
                scroll_amount = random.randint(300, 700)
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                
                # Jitter delay
                await self.random_delay(300, 800)
                
                # Randomly scroll slightly up occasionally
                if random.random() < 0.2:
                    await page.evaluate("window.scrollBy(0, -100)")
                    await self.random_delay(200, 400)
        except Exception as e:
            logger.warning(f"Error during human-like scrolling: {e}")

    async def random_delay(self, min_ms: int = 500, max_ms: int = 1500) -> None:
        """Asynchronously sleeps for a random amount of milliseconds."""
        delay = random.randint(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    def detect_bot_protection(self, html_content: str) -> bool:
        """
        Scans page markup for standard anti-bot / Cloudflare trigger signatures.
        """
        # Extract title from HTML content dynamically to check for successful loads
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        title_lower = title.lower()
        
        # If the page title matches standard shopping and search layouts, it is not blocked
        if any(keyword in title_lower for keyword in ["buy", "shop", "search", "price", "flipkart", "myntra"]):
            # Exclude actual Cloudflare/security blocks containing the site name
            if not any(cf in title_lower for cf in ["cloudflare", "attention required", "access denied", "just a moment"]):
                return False
                
        bot_signatures = [
            "robot check",
            "access denied",
            "attention required",
            "cloudflare",
            "verify you are human",
            "blocked request",
            "please wait while we verify"
        ]
        
        challenge_markers = [
            "id=\"challenge-form\"",
            "id=\"challenge-running\"",
            "class=\"cf-turnstile\"",
            "id=\"px-captcha\"",
            "g-recaptcha"
        ]
        
        lower_html = html_content.lower()
        
        # Check specific challenge elements in the markup
        for marker in challenge_markers:
            if marker.lower() in lower_html:
                return True
                
        # Check general bot signatures
        for signature in bot_signatures:
            if signature in lower_html:
                return True
                
        return False

    def clean_price(self, price_str: Optional[str]) -> float:
        """
        Strips currency symbols, commas, spaces, and formatting characters from a string,
        converting it to a clean float.
        """
        if not price_str:
            return 0.0
        try:
            # Strip out anything that isn't a digit, decimal point, or minus sign
            cleaned = re.sub(r"[^\d.]", "", price_str.replace(",", ""))
            if not cleaned:
                return 0.0
            return float(cleaned)
        except Exception:
            logger.warning(f"Failed to clean/parse price string: '{price_str}'")
            return 0.0

    def parse_review_count(self, count_str: Optional[str]) -> Optional[int]:
        """Extracts integers from review counts (e.g. '12,504 ratings' or '1.2k reviews' -> 12504)."""
        if not count_str:
            return None
        try:
            # Strip brackets, commas, spaces
            cleaned = count_str.replace(",", "").replace("(", "").replace(")", "").strip().lower()
            
            # Match formats like 1.2k, 15k
            k_match = re.search(r"([\d.]+)\s*k", cleaned)
            if k_match:
                val = float(k_match.group(1))
                return int(val * 1000)
                
            m_match = re.search(r"([\d.]+)\s*m", cleaned)
            if m_match:
                val = float(m_match.group(1))
                return int(val * 1000000)
                
            # Direct integer numbers extraction
            num_match = re.search(r"\d+", cleaned)
            if num_match:
                return int(num_match.group(0))
        except Exception as e:
            logger.warning(f"Could not parse review count '{count_str}': {e}")
        return None

    async def wait_for_page_settle(self, page: Page, timeout_ms: int = 3000) -> None:
        """Waits for navigation and network to settle before querying content."""
        try:
            await page.wait_for_load_state("load", timeout=timeout_ms)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

    async def get_page_content_safe(self, page: Page) -> str:
        """Retrieves page content safely, waiting for any active navigations to finish if needed."""
        for attempt in range(3):
            try:
                return await page.content()
            except Exception as e:
                err_msg = str(e)
                if "navigating" in err_msg.lower() or "navigation" in err_msg.lower():
                    logger.info("Page content retrieval deferred because page is actively navigating. Waiting for load state...")
                    try:
                        await page.wait_for_load_state("load", timeout=3000)
                    except Exception:
                        pass
                else:
                    raise
        # Final fallback
        return await page.content()

    async def execute_with_retry(self, action_func, platform: str) -> Any:
        """
        Executes a scraping operation within a Tenacity retry block.
        Only retries when a ScrapingBlockedError is raised (e.g. to cycle proxies/contexts).
        """
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_random_exponential(min=1, max=4),
                retry=retry_if_exception_type(ScrapingBlockedError),
                reraise=True
            ):
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        logger.info(f"Retrying scraping query on {platform} (Attempt {attempt.retry_state.attempt_number})")
                    return await action_func()
        except ScrapingBlockedError as sbe:
            logger.error(f"Scraping permanently blocked on {platform} after multiple attempts: {sbe}")
            raise
        except Exception as e:
            logger.error(f"Unretryable exception occurred on {platform}: {e}")
            raise
