import asyncio
from typing import List, Dict, Any, Type
from src.schemas.product import Product
from src.scrapers.base import BaseScraper
from src.scrapers.amazon import AmazonScraper
from src.scrapers.flipkart import FlipkartScraper
from src.scrapers.meesho import MeeshoScraper
from src.scrapers.myntra import MyntraScraper
from src.core.cache import get_search_cache, set_search_cache
from src.core.logger import logger
from src.core.exceptions import PlatformNotSupportedError

SCRAPER_MAP: Dict[str, Type[BaseScraper]] = {
    "amazon": AmazonScraper,
    "flipkart": FlipkartScraper,
    "meesho": MeeshoScraper,
    "myntra": MyntraScraper
}

async def search_products_logic(
    query: str, 
    platforms: List[str] = ["amazon", "flipkart", "meesho", "myntra"], 
    limit: int = 5
) -> List[Product]:
    """
    Core logic to search products across selected platforms.
    Performs parallel scraping with caching verification.
    """
    if not query:
        return []
        
    query_clean = query.lower().strip()
    platforms_clean = [p.lower().strip() for p in platforms]
    
    # Validate platform support
    for p in platforms_clean:
        if p not in SCRAPER_MAP:
            raise PlatformNotSupportedError(f"Platform '{p}' is not supported. Supported: {list(SCRAPER_MAP.keys())}")

    results: List[Product] = []
    pending_scrapes: List[asyncio.Task] = []
    task_to_platform: Dict[asyncio.Task, str] = {}

    for platform in platforms_clean:
        # 1. Try checking cache first
        try:
            cached_data = await get_search_cache(platform, query_clean, limit)
            if cached_data is not None:
                logger.info(f"Cache HIT for platform '{platform}' and query: '{query_clean}'")
                for item_dict in cached_data:
                    results.append(Product(**item_dict))
                continue
        except Exception as e:
            logger.warning(f"Error checking cache for '{platform}': {e}")

        # 2. Cache MISS: Queue scraping task
        scraper_cls = SCRAPER_MAP[platform]
        scraper = scraper_cls()
        
        # Define coroutine execution
        coro = scraper.search(query_clean, limit=limit)
        task = asyncio.create_task(coro)
        pending_scrapes.append(task)
        task_to_platform[task] = platform

    # 3. Execute all missing platform scrapes concurrently
    if pending_scrapes:
        logger.info(f"Executing search on {len(pending_scrapes)} platforms in parallel for: '{query_clean}'")
        scraping_results = await asyncio.gather(*pending_scrapes, return_exceptions=True)

        for i, val in enumerate(scraping_results):
            task = pending_scrapes[i]
            platform = task_to_platform[task]

            if isinstance(val, Exception):
                logger.error(f"Scraper error on platform '{platform}' for query '{query_clean}': {val}")
                # Continue gathering results from other successful platforms
                continue
                
            if val:
                # Add to results
                results.extend(val)
                # Store in SQLite cache asynchronously
                try:
                    results_dicts = [item.model_dump() for item in val]
                    await set_search_cache(platform, query_clean, limit, results_dicts)
                except Exception as cache_err:
                    logger.warning(f"Failed to cache search results for '{platform}': {cache_err}")

    # Return aggregated list
    return results
