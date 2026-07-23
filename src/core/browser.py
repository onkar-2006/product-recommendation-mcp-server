import asyncio
import contextlib
import random
import sys
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from config.settings import settings
from src.core.logger import logger
from src.core.exceptions import BrowserInitializationError

def ensure_playwright_chromium() -> None:
    """Auto-detects and installs the Playwright Chromium binary if missing (required for serverless cloud environments)."""
    import os
    import subprocess
    import sys
    
    # Check PLAYWRIGHT_BROWSERS_PATH from environment if set, else fallback to home cache
    if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
        cache_path = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
        logger.info(f"Using PLAYWRIGHT_BROWSERS_PATH from environment: {cache_path}")
    else:
        home = os.path.expanduser("~")
        cache_path = os.path.join(home, ".cache", "ms-playwright")
        logger.info(f"Using default home cache path: {cache_path}")
    
    has_chromium = False
    if os.path.exists(cache_path):
        for root, dirs, files in os.walk(cache_path):
            if "chrome-linux" in root or "chrome" in files or "chrome.exe" in files or "chrome-headless-shell" in files:
                has_chromium = True
                break
                
    if not has_chromium:
        logger.info(f"Playwright Chromium browser binary not found in {cache_path}. Auto-installing...")
        try:
            # Invokes 'playwright install chromium' using the current Python execution context
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            logger.info("Playwright Chromium browser installed successfully.")
        except Exception as e:
            logger.error(f"Failed to auto-install Playwright Chromium: {e}")
    else:
        logger.info(f"Playwright Chromium browser binary already verified in {cache_path}.")

# List of modern, realistic user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

STEALTH_INIT_SCRIPT = """
// Mask navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Spoof navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// Spoof WebGL vendor and renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
        return 'Intel Inc.';
    }
    if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
        return 'Intel(R) Iris(TM) Plus Graphics 640';
    }
    return getParameter.apply(this, arguments);
};

// Spoof navigator.plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
    ]
});
"""

class BrowserManager:
    """
    Singleton manager of the Playwright browser process.
    Handles concurrency throttling, context isolation, browser crash recovery,
    and anti-bot stealth configurations.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize properties once
        if not hasattr(self, "_initialized"):
            self._playwright: Playwright | None = None
            self._browser: Browser | None = None
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_contexts)
            self._initialized = True

    async def _start_browser(self) -> None:
        """Starts a fresh browser process."""
        logger.info("Initializing Playwright engine...")
        
        # Ensure browser binaries are present dynamically before starting Playwright
        await asyncio.to_thread(ensure_playwright_chromium)
        
        try:
            self._playwright = await async_playwright().start()
            
            # Setup proxy settings if defined in config
            proxy = None
            if settings.proxy_server:
                proxy = {"server": settings.proxy_server}
                if settings.proxy_username and settings.proxy_password:
                    proxy["username"] = settings.proxy_username
                    proxy["password"] = settings.proxy_password
                logger.info(f"Configuring global browser proxy: {settings.proxy_server}")

            # Realistic launch arguments to prevent bot detection flags
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--disable-dev-shm-usage",
                "--disable-gpu" if sys.platform != "win32" else "" # GPU disabled in Linux containers
            ]
            launch_args = [arg for arg in launch_args if arg]

            self._browser = await self._playwright.chromium.launch(
                headless=settings.headless,
                args=launch_args,
                proxy=proxy
            )
            logger.info("Playwright Chromium browser started successfully.")
        except Exception as e:
            logger.error(f"Failed to start Playwright browser: {e}")
            await self._close_under_lock()
            raise BrowserInitializationError(f"Playwright start failure: {e}")

    async def _close_under_lock(self) -> None:
        """Internal cleanup helper. Must only be called while holding self._lock."""
        try:
            if self._browser:
                logger.info("Closing browser process...")
                await self._browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            self._browser = None

        try:
            if self._playwright:
                logger.info("Stopping Playwright engine...")
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error stopping Playwright: {e}")
        finally:
            self._playwright = None

    async def get_browser(self) -> Browser:
        """
        Thread-safe singleton getter.
        Automatically heals and restarts the browser if it has crashed or closed.
        """
        async with self._lock:
            # Check if browser needs starting or has been closed/disconnected
            if not self._browser or not self._browser.is_connected():
                logger.info("Browser is disconnected or uninitialized. Spawning fresh process...")
                await self._close_under_lock() # Clean up any stale sockets first
                await self._start_browser()
            return self._browser

    @contextlib.asynccontextmanager
    async def page_context(self) -> AsyncGenerator[Page, None]:
        """
        Async context manager providing a throttled, stealth-configured incognito Page.
        Usage:
            async with browser_manager.page_context() as page:
                await page.goto("https://...")
        """
        # 1. Throttling: block until a slot is available under the Semaphore
        await self._semaphore.acquire()
        
        context: BrowserContext | None = None
        page: Page | None = None
        
        try:
            browser = await self.get_browser()
            
            # 2. Context configuration (Incognito, unique User-Agent & Viewport)
            ua = random.choice(USER_AGENTS)
            width = random.randint(1280, 1920)
            height = random.randint(720, 1080)
            
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": width, "height": height},
                accept_downloads=False,
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Upgrade-Insecure-Requests": "1"
                }
            )
            
            # Set default navigation timeout
            context.set_default_timeout(settings.timeout_ms)
            
            # 3. Apply Stealth Injections on Document Creation
            if settings.stealth_mode:
                await context.add_init_script(STEALTH_INIT_SCRIPT)
                
            page = await context.new_page()
            yield page
            
        except Exception as e:
            logger.error(f"Error during browser page lifecycle: {e}")
            raise
        finally:
            # 4. Clean up resources immediately to release RAM and exit context slot
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
            except Exception as e:
                logger.warning(f"Error during page/context cleanup: {e}")
            finally:
                self._semaphore.release()

    async def close(self) -> None:
        """Gracefully shuts down the browser and releases Playwright resources."""
        async with self._lock:
            await self._close_under_lock()
            logger.info("Playwright browser resources fully released.")

# Global singleton exporter
browser_manager = BrowserManager()
