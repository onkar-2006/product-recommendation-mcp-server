from src.schemas.product import ProductDetails
from src.tools.search import SCRAPER_MAP
from src.core.cache import get_details_cache, set_details_cache
from src.core.logger import logger
from src.core.exceptions import PlatformNotSupportedError, ProductNotFoundError

async def get_product_details_logic(url: str, platform: str) -> ProductDetails:
    """
    Fetches comprehensive product specifications, descriptions, and ratings
    for a direct product URL. Uses caching to prevent duplicate hits.
    """
    if not url:
        raise ValueError("URL parameter is required.")
        
    plat_key = platform.lower().strip()
    if plat_key not in SCRAPER_MAP:
        raise PlatformNotSupportedError(
            f"Platform '{platform}' is not supported. Supported platforms: {list(SCRAPER_MAP.keys())}"
        )

    # 1. Try checking SQLite cache first
    try:
        cached_data = await get_details_cache(url)
        if cached_data is not None:
            logger.info(f"Cache PDP HIT for URL: {url}")
            return ProductDetails(**cached_data)
    except Exception as e:
        logger.warning(f"Error checking details cache for URL '{url}': {e}")

    # 2. Cache MISS: Run scraper extraction
    scraper_cls = SCRAPER_MAP[plat_key]
    scraper = scraper_cls()
    
    logger.info(f"Cache PDP MISS. Scraping details for URL: {url}")
    details = await scraper.get_details(url)
    
    if not details:
        raise ProductNotFoundError(f"Failed to scrape product details from URL: '{url}'")

    # 3. Cache the successful result
    try:
        await set_details_cache(url, details.model_dump())
    except Exception as cache_err:
        logger.warning(f"Failed to cache product details for URL '{url}': {cache_err}")
        
    return details
