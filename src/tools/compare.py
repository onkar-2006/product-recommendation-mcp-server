from typing import List, Optional
from src.schemas.product import Product, CompareResult
from src.tools.search import search_products_logic
from src.core.logger import logger

async def compare_prices_logic(
    query: str, 
    platforms: List[str] = ["amazon", "flipkart", "meesho", "myntra"]
) -> CompareResult:
    """
    Scrapes selected platforms for a search query, pools all results,
    sorts them by price ascending, and identifies the absolute cheapest item.
    """
    logger.info(f"Comparing prices for: '{query}' across platforms: {platforms}")
    
    # Use search logic to get all platform products (limit to 5 per platform for a solid pool)
    products = await search_products_logic(query, platforms=platforms, limit=5)
    
    if not products:
        return CompareResult(query=query, cheapest=None, results=[])

    # Filter out items with invalid prices (0.0 or lower)
    valid_products = [p for p in products if p.price > 0.0]
    
    # Sort products by price (ascending)
    sorted_products = sorted(valid_products, key=lambda p: p.price)
    
    cheapest_item: Optional[Product] = None
    if sorted_products:
        cheapest_item = sorted_products[0]
        logger.info(f"Cheapest item identified: {cheapest_item.title} on {cheapest_item.platform} for INR {cheapest_item.price}")
        
    return CompareResult(
        query=query,
        cheapest=cheapest_item,
        results=sorted_products
    )
